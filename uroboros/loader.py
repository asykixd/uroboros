"""Загрузка, выгрузка и реестр модулей."""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import itertools
import logging
import re
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any

from . import __version__, download, github
from .database import LOADER_OWNER, Database, ModuleDB
from .decorators import (
    CALLBACK_ATTR,
    COMMAND_ATTR,
    INLINE_ATTR,
    WATCHER_ATTR,
    CallbackHandlerInfo,
    CommandInfo,
    InlineHandlerInfo,
    WatcherInfo,
)
from .errors import LoadError
from .inline import Inline
from .loops import LOOP_ATTR, Loop
from .security import Security
from .types import Library, Module, ModuleConfig, Strings

if TYPE_CHECKING:
    from telethon import TelegramClient

    from .dispatcher import Dispatcher
    from .inline import InlineManager

log = logging.getLogger(__name__)

BUILTIN_DIR = Path(__file__).parent / "modules"
REQUIRES_RE = re.compile(r"^\s*#\s*requires:\s*(.+)$", re.MULTILINE)
META_RE = re.compile(r"^\s*#\s*meta\s+(\w+)\s*:\s*(.+?)\s*$", re.MULTILINE)
REQUIRES_CORE_RE = re.compile(r"^\s*#\s*requires_uroboros\s*:\s*(?:>=)?\s*(\S+)\s*$", re.MULTILINE)

Handler = Callable[[Any], Awaitable[Any]]


@dataclass
class Command:
    info: CommandInfo
    func: Handler
    module: Module

    @property
    def name(self) -> str:
        return self.info.name


@dataclass
class Watcher:
    info: WatcherInfo
    func: Handler
    module: Module

    def matches(self, message: Any) -> bool:
        if self.info.only_outgoing and not message.out:
            return False
        if self.info.only_incoming and message.out:
            return False
        return self.info.filter is None or bool(self.info.filter(message))


@dataclass
class InlineHandler:
    info: InlineHandlerInfo
    func: Handler
    module: Module


@dataclass
class CallbackHandler:
    info: CallbackHandlerInfo
    func: Handler
    module: Module

    def matches(self, data: str) -> bool:
        return self.info.prefix is None or data.startswith(self.info.prefix)


def parse_requires(source: str) -> list[str]:
    return [pkg for match in REQUIRES_RE.findall(source) for pkg in match.split()]


def parse_meta(source: str) -> dict[str, str]:
    """``# meta developer: @me`` → ``{"developer": "@me"}``."""
    return {key.lower(): value for key, value in META_RE.findall(source)}


def version_tuple(version: str) -> tuple[int, ...]:
    """``"0.2"`` → ``(0, 2, 0)``, ``"0.1.1b2"`` → ``(0, 1, 1)``: суффиксы бет не учитываются."""
    match = re.match(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", version.strip())
    if not match:
        raise ValueError(version)
    return tuple(int(part or 0) for part in match.groups())


# Признаки модулей Hikka/FTG: относительный импорт ядра, их форк Telethon, @loader.tds.
HIKKA_RE = re.compile(
    r"^\s*from\s+\.\.(?:\s+import\b|\w)"
    r"|^\s*(?:from|import)\s+(?:hikkatl|hikka|telethon_hikka)\b"
    r"|^\s*@loader\.tds\b",
    re.MULTILINE,
)


def check_not_hikka(source: str) -> None:
    """Модули Hikka/FTG без адаптера падают на непонятной ошибке — останавливаем их заранее."""
    if HIKKA_RE.search(source):
        raise LoadError(
            "Это модуль Hikka/FTG, Uroboros пока не умеет их загружать. "
            "Совместимость с модулями Hikka запланирована в версии 0.6"
        )


def check_core_version(source: str) -> None:
    match = REQUIRES_CORE_RE.search(source)
    if not match:
        return
    try:
        required = version_tuple(match[1])
    except ValueError:
        raise LoadError(f"Непонятная версия в requires_uroboros: {match[1]}") from None
    if version_tuple(__version__) < required:
        raise LoadError(f"Модулю нужен Uroboros {match[1]} или новее, установлен {__version__}. Обновитесь: .update")


@dataclass
class LoadedLib:
    obj: Any  # экземпляр Library или Python-модуль
    modname: str
    users: set[str]  # stem'ы модулей, которые её подключили


def lib_file_name(url: str) -> str:
    """Имя файла кеша: читаемое начало и хеш ссылки, чтобы не было коллизий."""
    base = make_stem(url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".py"))[:40]
    return f"{base}_{hashlib.sha256(url.encode()).hexdigest()[:10]}.py"


def make_stem(name: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", name.lower()) or "module"


async def pip_install(packages: list[str]) -> None:
    log.info("Устанавливаю зависимости: %s", " ".join(packages))
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "-q",
        *packages,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    output, _ = await proc.communicate()
    if proc.returncode != 0:
        raise LoadError(
            f"Не удалось установить зависимости ({' '.join(packages)}):\n" + output.decode(errors="replace")[-1000:]
        )
    importlib.invalidate_caches()


class Loader:
    def __init__(self, client: TelegramClient | None, db: Database, modules_dir: Path):
        self.client = client
        self.db = db
        self.modules_dir = modules_dir
        self.dispatcher: Dispatcher | None = None
        self.inline: InlineManager | None = None
        self.security = Security(db)

        self.modules: dict[str, Module] = {}  # имя в нижнем регистре → модуль
        self.commands: dict[str, Command] = {}  # основное имя → команда
        self.command_aliases: dict[str, str] = {}  # алиас из @command → основное имя
        self.watchers: list[Watcher] = []
        self.inline_handlers: dict[str, InlineHandler] = {}  # имя → обработчик @бот <имя>
        self.callback_handlers: list[CallbackHandler] = []
        self.libs: dict[str, LoadedLib] = {}  # url → библиотека
        self._counter = itertools.count()

    # --- поиск ---

    def get_module(self, name: str) -> Module | None:
        return self.modules.get(name.lower())

    def get_command(self, name: str) -> Command | None:
        name = name.lower()
        return self.commands.get(name) or self.commands.get(self.command_aliases.get(name, ""))

    def module_commands(self, module: Module) -> list[Command]:
        return [cmd for cmd in self.commands.values() if cmd.module is module]

    def installed(self) -> dict[str, str]:
        """Сторонние модули: имя файла (stem) → источник (URL или file:...)."""
        return self.db.get(LOADER_OWNER, "installed", {})

    # --- загрузка ---

    async def load_all(self) -> None:
        for path in sorted(BUILTIN_DIR.glob("*.py")):
            if path.name.startswith("_"):
                continue
            try:
                await self.load_source(path.read_text("utf-8"), origin="builtin", stem=path.stem, filename=str(path))
            except Exception:
                log.exception("Не удалось загрузить встроенный модуль %s", path.stem)

        for stem, origin in self.installed().items():
            path = self.modules_dir / f"{stem}.py"
            if not path.exists():
                log.warning("Файл модуля %s пропал, пропускаю", path)
                continue
            try:
                await self.load_source(path.read_text("utf-8"), origin=origin, stem=stem, filename=str(path))
            except Exception:
                log.exception("Не удалось загрузить модуль %s", stem)

        log.info("Загружено модулей: %d, команд: %d", len(self.modules), len(self.commands))

    async def load_source(
        self,
        source: str,
        *,
        origin: str,
        stem: str | None = None,
        filename: str | None = None,
    ) -> list[Module]:
        instances, _ = await self._load(source, origin=origin, stem=stem, filename=filename)
        return instances

    async def install(self, source: str, origin: str) -> list[Module]:
        """Загружает сторонний модуль и сохраняет его, чтобы он грузился после рестарта."""
        installed = self.installed()
        instances, replaced = await self._load(source, origin=origin)
        stem = instances[0]._stem

        if stem not in installed:
            for inst in instances:
                try:
                    await inst.on_dlmod()
                except Exception as e:
                    log.exception("Ошибка в on_dlmod модуля %s", inst.name)
                    await self.unload_stem(stem)
                    detail = str(e) if isinstance(e, LoadError) else repr(e)
                    raise LoadError(f"Ошибка при первой настройке модуля {inst.name}: {detail}") from e

        for old_stem in replaced - {stem}:
            installed.pop(old_stem, None)
            (self.modules_dir / f"{old_stem}.py").unlink(missing_ok=True)

        self.modules_dir.mkdir(parents=True, exist_ok=True)
        (self.modules_dir / f"{stem}.py").write_bytes(source.encode("utf-8"))
        installed[stem] = origin
        self.db.set(LOADER_OWNER, "installed", installed)
        return instances

    async def _load(
        self,
        source: str,
        *,
        origin: str,
        stem: str | None = None,
        filename: str | None = None,
    ) -> tuple[list[Module], set[str]]:
        builtin = origin == "builtin"
        if builtin:
            modname = f"uroboros.modules.{stem}"
        else:
            modname = f"uroboros.ext.{stem or 'module'}_{next(self._counter)}"

        check_not_hikka(source)
        check_core_version(source)
        meta = parse_meta(source)
        try:
            code = compile(source, filename or f"<{origin}>", "exec")
        except SyntaxError as e:
            raise LoadError(f"Синтаксическая ошибка: {e}") from e

        pymod = await self._exec(code, modname, source)
        classes = [
            obj
            for obj in vars(pymod).values()
            if isinstance(obj, type) and issubclass(obj, Module) and obj is not Module and obj.__module__ == modname
        ]
        if not classes:
            sys.modules.pop(modname, None)
            raise LoadError("В файле нет ни одного класса-наследника Module")

        instances = [cls() for cls in classes]
        stem = stem or make_stem(instances[0].name)

        # Какие уже загруженные файлы заменяются этим.
        replaced: set[str] = set()
        for inst in instances:
            old = self.get_module(inst.name)
            if old is None:
                continue
            if old.is_builtin and not builtin:
                sys.modules.pop(modname, None)
                raise LoadError(f"Нельзя заменить встроенный модуль {old.name}")
            replaced.add(old._stem)

        # Конфликты команд с модулями, которые останутся после замены.
        taken = {
            name: cmd.module.name
            for cmd in self.commands.values()
            if cmd.module._stem not in replaced
            for name in (cmd.name, *cmd.info.aliases)
        }
        for inst in instances:
            for info, _ in self._collect(inst, COMMAND_ATTR):
                for name in (info.name, *info.aliases):
                    if name in taken:
                        sys.modules.pop(modname, None)
                        raise LoadError(f"Команда {name} уже занята модулем {taken[name]}")
                    taken[name] = inst.name

        taken_inline = {
            name: handler.module.name
            for name, handler in self.inline_handlers.items()
            if handler.module._stem not in replaced
        }
        for inst in instances:
            for info, _ in self._collect(inst, INLINE_ATTR):
                if info.name in taken_inline:
                    sys.modules.pop(modname, None)
                    raise LoadError(f"Inline-команда {info.name} уже занята модулем {taken_inline[info.name]}")
                taken_inline[info.name] = inst.name

        for old_stem in replaced:
            await self.unload_stem(old_stem)

        for inst in instances:
            inst._stem = stem
            inst._origin = origin
            inst._meta = meta
            inst.strings = Strings(inst.strings)
            inst.client = self.client
            inst.loader = self
            inst.db = ModuleDB(self.db, inst.name)
            inst.inline = Inline(self, inst)
            if isinstance(inst.config, ModuleConfig):
                inst.config._bind(inst.db)
            self._register(inst)

        for inst in instances:
            try:
                await inst.on_load()
            except Exception as e:
                log.exception("Ошибка в on_load модуля %s", inst.name)
                await self.unload_stem(stem)
                detail = str(e) if isinstance(e, LoadError) else repr(e)
                raise LoadError(f"Ошибка при запуске модуля {inst.name}: {detail}") from e

        for inst in instances:
            for task in inst._loops:
                if task.info.autostart:
                    task.start()
            log.info("Загружен модуль %s (%s)", inst.name, origin)
        return instances, replaced

    async def _exec(self, code, modname: str, source: str) -> ModuleType:
        installed_requirements = False
        while True:
            pymod = ModuleType(modname)
            pymod.__file__ = code.co_filename
            sys.modules[modname] = pymod
            try:
                exec(code, pymod.__dict__)
                return pymod
            except ImportError as e:
                sys.modules.pop(modname, None)
                requirements = parse_requires(source)
                if installed_requirements or not requirements:
                    raise LoadError(f"Не хватает зависимости: {e}") from e
                await pip_install(requirements)
                installed_requirements = True
            except BaseException:
                sys.modules.pop(modname, None)
                raise

    @staticmethod
    def _collect(inst: Module, attr: str) -> list[tuple[Any, Handler]]:
        found = []
        for name in dir(type(inst)):
            func = getattr(type(inst), name, None)
            info = getattr(func, attr, None)
            if info is not None:
                found.append((info, getattr(inst, name)))
        return found

    def _register(self, inst: Module) -> None:
        self.modules[inst.name.lower()] = inst
        for info, func in self._collect(inst, COMMAND_ATTR):
            self.commands[info.name] = Command(info, func, inst)
            for alias in info.aliases:
                self.command_aliases[alias] = info.name
        for info, func in self._collect(inst, WATCHER_ATTR):
            self.watchers.append(Watcher(info, func, inst))
        for info, func in self._collect(inst, INLINE_ATTR):
            self.inline_handlers[info.name] = InlineHandler(info, func, inst)
        for info, func in self._collect(inst, CALLBACK_ATTR):
            self.callback_handlers.append(CallbackHandler(info, func, inst))
        inst._loops = []
        for info, func in self._collect(inst, LOOP_ATTR):
            task = Loop(func, info, inst.name)
            setattr(inst, func.__name__, task)  # self.<метод> — управление задачей
            inst._loops.append(task)

    # --- библиотеки ---

    @property
    def libs_dir(self) -> Path:
        return self.modules_dir / "libs"

    async def import_lib(self, url: str, user: Module, *, reload: bool = False) -> Any:
        url = github.to_raw_url(url) or url
        entry = self.libs.get(url)
        if entry is not None and not reload:
            entry.users.add(user._stem)
            return entry.obj

        source = await self._lib_source(url, refresh=reload)
        obj, modname = await self._load_lib(source, url)
        users = {user._stem}
        if entry is not None:
            users |= entry.users
            await self._unload_lib(url)
        self.libs[url] = LoadedLib(obj, modname, users)
        return obj

    async def _lib_source(self, url: str, *, refresh: bool) -> str:
        cache = self.db.get(LOADER_OWNER, "libs", {})
        path = self.libs_dir / cache.get(url, lib_file_name(url))
        if path.exists() and not refresh:
            return path.read_bytes().decode("utf-8")
        source = await download.download_source(url)
        self.libs_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(source.encode("utf-8"))
        cache[url] = path.name
        self.db.set(LOADER_OWNER, "libs", cache)
        return source

    async def _load_lib(self, source: str, url: str) -> tuple[Any, str]:
        check_not_hikka(source)
        check_core_version(source)
        modname = f"uroboros.lib.{lib_file_name(url).removesuffix('.py')}_{next(self._counter)}"
        try:
            code = compile(source, f"<{url}>", "exec")
        except SyntaxError as e:
            raise LoadError(f"Синтаксическая ошибка в библиотеке {url}: {e}") from e
        pymod = await self._exec(code, modname, source)

        classes = [
            obj
            for obj in vars(pymod).values()
            if isinstance(obj, type) and issubclass(obj, Library) and obj is not Library and obj.__module__ == modname
        ]
        if not classes:
            return pymod, modname
        if len(classes) > 1:
            sys.modules.pop(modname, None)
            raise LoadError(f"В библиотеке {url} больше одного класса Library")

        lib = classes[0]()
        lib.client = self.client
        lib.loader = self
        lib.db = ModuleDB(self.db, f"lib.{lib.name}")
        lib.inline = Inline(self, None)
        try:
            await lib.on_load()
        except Exception as e:
            sys.modules.pop(modname, None)
            raise LoadError(f"Ошибка при запуске библиотеки {lib.name}: {e!r}") from e
        log.info("Загружена библиотека %s (%s)", lib.name, url)
        return lib, modname

    async def _unload_lib(self, url: str) -> None:
        entry = self.libs.pop(url)
        if isinstance(entry.obj, Library):
            try:
                await entry.obj.on_unload()
            except Exception:
                log.exception("Ошибка в on_unload библиотеки %s", entry.obj.name)
        sys.modules.pop(entry.modname, None)

    async def _release_libs(self, stem: str) -> None:
        """Модуль выгружен: библиотеки, которые больше никому не нужны, выгружаются тоже."""
        for url, entry in list(self.libs.items()):
            entry.users.discard(stem)
            if not entry.users:
                await self._unload_lib(url)

    # --- выгрузка ---

    async def unload_stem(self, stem: str) -> list[Module]:
        """Выгружает все модули, загруженные из одного файла."""
        removed = [m for m in self.modules.values() if m._stem == stem]
        for inst in removed:
            for task in inst._loops:
                await task.wait_stopped()
            try:
                await inst.on_unload()
            except Exception:
                log.exception("Ошибка в on_unload модуля %s", inst.name)
            self._remove_event_handlers(inst)

            for name, cmd in list(self.commands.items()):
                if cmd.module is inst:
                    del self.commands[name]
                    for alias in cmd.info.aliases:
                        self.command_aliases.pop(alias, None)
            self.watchers = [w for w in self.watchers if w.module is not inst]
            self.inline_handlers = {n: h for n, h in self.inline_handlers.items() if h.module is not inst}
            self.callback_handlers = [h for h in self.callback_handlers if h.module is not inst]
            self.modules.pop(inst.name.lower(), None)
            sys.modules.pop(type(inst).__module__, None)
        if self.inline is not None:
            self.inline.release(stem)
        await self._release_libs(stem)
        return removed

    def _remove_event_handlers(self, inst: Module) -> None:
        """Снимает обработчики, которые модуль повесил через ``client.add_event_handler``.

        Обработчик считается принадлежащим модулю, если это его метод или функция
        (в том числе замыкание или lambda), объявленная в файле модуля.
        """
        if self.client is None:
            return
        modname = type(inst).__module__
        for callback, _ in self.client.list_event_handlers():
            func = getattr(callback, "__func__", callback)
            if getattr(callback, "__self__", None) is inst or getattr(func, "__module__", None) == modname:
                self.client.remove_event_handler(callback)

    async def uninstall(self, name: str) -> list[Module]:
        """Удаляет сторонний модуль (и всё, что лежит в том же файле)."""
        inst = self.get_module(name)
        if inst is None:
            raise LoadError(f"Модуль {name} не найден")
        if inst.is_builtin:
            raise LoadError(f"{inst.name} — встроенный модуль, его нельзя удалить")

        stem = inst._stem
        removed = await self.unload_stem(stem)
        installed = self.installed()
        installed.pop(stem, None)
        self.db.set(LOADER_OWNER, "installed", installed)
        (self.modules_dir / f"{stem}.py").unlink(missing_ok=True)
        return removed

    async def unload_all(self) -> None:
        """Выгружает всё в порядке, обратном загрузке: сначала сторонние, потом встроенные."""
        stems = list(dict.fromkeys(m._stem for m in self.modules.values()))
        for stem in reversed(stems):
            await self.unload_stem(stem)

    async def reload_all(self) -> None:
        await self.unload_all()
        await self.load_all()
