"""``from .. import loader``: API модулей Hikka поверх Uroboros.

Декораторы Hikka только помечают методы (как в Hikka). При создании класса-наследника
``loader.Module`` метки переводятся в команды, вотчеры, inline-обработчики и фоновые
задачи Uroboros. Поведение повторяет Hikka (AGPL-3.0, https://github.com/hikariatama/Hikka).
"""

from __future__ import annotations

import ast
import asyncio
import contextlib
import functools
import inspect
import logging
import re
from typing import Any

from .. import types as core
from ..decorators import (
    CALLBACK_ATTR,
    COMMAND_ATTR,
    INLINE_ATTR,
    WATCHER_ATTR,
    CallbackHandlerInfo,
    CommandInfo,
    InlineHandlerInfo,
    WatcherInfo,
)
from ..errors import LoadError
from ..loops import LOOP_ATTR, LoopInfo, StopLoop
from . import security, state, utils, validators
from .inline_adapter import HikkaCall, HikkaInline, HikkaInlineQuery, convert_inline_results
from .inline_adapter import HikkaInlineMessage as InlineMessage
from .security import (
    group_admin,
    group_admin_add_admins,
    group_admin_ban_users,
    group_admin_change_info,
    group_admin_delete_messages,
    group_admin_invite_users,
    group_admin_pin_messages,
    group_member,
    group_owner,
    inline_everyone,
    owner,
    pm,
    sudo,
    support,
    unrestricted,
)

log = logging.getLogger(__name__)

__all__ = [
    "ConfigValue",
    "CoreOverwriteError",
    "CoreUnloadError",
    "InfiniteLoop",
    "InlineMessage",
    "Library",
    "LibraryConfig",
    "LoadError",
    "Module",
    "ModuleConfig",
    "SelfSuspend",
    "SelfUnload",
    "StopLoop",
    "callback_handler",
    "command",
    "group_admin",
    "group_admin_add_admins",
    "group_admin_ban_users",
    "group_admin_change_info",
    "group_admin_delete_messages",
    "group_admin_invite_users",
    "group_admin_pin_messages",
    "group_member",
    "group_owner",
    "inline_everyone",
    "inline_handler",
    "loop",
    "owner",
    "pm",
    "raw_handler",
    "sudo",
    "support",
    "tag",
    "tds",
    "unrestricted",
    "validators",
    "watcher",
]


class SelfUnload(Exception):
    """Модуль просит выгрузить себя."""


class SelfSuspend(Exception):
    """Модуль просит приостановить себя."""


class CoreOverwriteError(LoadError):
    pass


class CoreUnloadError(Exception):
    pass


# --- декораторы-метки ---


def _mark(mark: str, *args: Any, **kwargs: Any):
    def decorator(func):
        setattr(func, mark, True)
        for arg in args:
            setattr(func, arg, True)
        for key, value in kwargs.items():
            setattr(func, key, value)
        return func

    return decorator


def command(*args: Any, **kwargs: Any):
    return _mark("is_command", *args, **kwargs)


def watcher(*args: Any, **kwargs: Any):
    return _mark("is_watcher", *args, **kwargs)


def inline_handler(*args: Any, **kwargs: Any):
    return _mark("is_inline_handler", *args, **kwargs)


def callback_handler(*args: Any, **kwargs: Any):
    return _mark("is_callback_handler", *args, **kwargs)


def debug_method(*args: Any, **kwargs: Any):
    return _mark("is_debug_method", *args, **kwargs)


def tag(*tags: str, **kwarg_tags: Any):
    def decorator(func):
        for name in tags:
            setattr(func, name, True)
        for name, value in kwarg_tags.items():
            setattr(func, name, value)
        return func

    return decorator


def ratelimit(func):
    func.ratelimit = True
    return func


def raw_handler(*updates: Any):
    def decorator(func):
        func.is_raw_handler = True
        func.updates = updates
        return func

    return decorator


def tds(cls):
    """В Hikka переводит докстринги; в Uroboros интерфейс только на русском — ничего не делает."""
    return cls


translatable_docstring = tds


class InfiniteLoop:
    """То, что возвращает ``@loader.loop``: при создании класса превращается в ``@loop`` Uroboros."""

    def __init__(self, func, interval: float, autostart: bool, wait_before: bool, stop_clause: str | None):
        self.func = func
        self.interval = interval
        self.autostart = autostart
        self.wait_before = wait_before
        self.stop_clause = stop_clause


def loop(interval: float = 5, autostart: bool = False, wait_before: bool = False, stop_clause: str | None = None):
    def decorator(func):
        return InfiniteLoop(func, interval, autostart, wait_before, stop_clause)

    return decorator


# --- теги вотчеров и команд ---


def _is_command(message: Any) -> bool:
    if state.loader is None or not getattr(message, "raw_text", None):
        return False
    from ..dispatcher import parse_command
    from ..utils import get_prefix

    return parse_command(message.raw_text, get_prefix(state.loader.db)) is not None


def _chat_matches(message: Any, chat_id: Any) -> bool:
    text = str(chat_id)
    expected = int(text[4:]) if text.startswith("-100") else int(text)
    return utils.get_chat_id(message) == abs(expected) or message.chat_id == int(text)


_TAGS = {
    "out": lambda m, f: getattr(m, "out", True),
    "in": lambda m, f: not getattr(m, "out", True),
    "only_messages": lambda m, f: True,
    "editable": lambda m, f: (
        not getattr(m, "out", False)
        and not getattr(m, "fwd_from", None)
        and not getattr(m, "sticker", None)
        and not getattr(m, "via_bot_id", None)
    ),
    "no_media": lambda m, f: not getattr(m, "media", None),
    "only_media": lambda m, f: bool(getattr(m, "media", None)),
    "only_photos": lambda m, f: utils.mime_type(m).startswith("image/"),
    "only_videos": lambda m, f: utils.mime_type(m).startswith("video/"),
    "only_audios": lambda m, f: utils.mime_type(m).startswith("audio/"),
    "only_stickers": lambda m, f: bool(getattr(m, "sticker", None)),
    "only_docs": lambda m, f: bool(getattr(m, "document", None)),
    "only_inline": lambda m, f: bool(getattr(m, "via_bot_id", None)),
    "only_channels": lambda m, f: getattr(m, "is_channel", False) and not getattr(m, "is_group", False),
    "no_channels": lambda m, f: not getattr(m, "is_channel", False),
    "only_groups": lambda m, f: getattr(m, "is_group", False),
    "no_groups": lambda m, f: not getattr(m, "is_group", False),
    "only_pm": lambda m, f: getattr(m, "is_private", False),
    "no_pm": lambda m, f: not getattr(m, "is_private", False),
    "no_inline": lambda m, f: not getattr(m, "via_bot_id", None),
    "no_stickers": lambda m, f: not getattr(m, "sticker", None),
    "no_docs": lambda m, f: not getattr(m, "document", None),
    "no_audios": lambda m, f: not utils.mime_type(m).startswith("audio/"),
    "no_videos": lambda m, f: not utils.mime_type(m).startswith("video/"),
    "no_photos": lambda m, f: not utils.mime_type(m).startswith("image/"),
    "no_forwards": lambda m, f: not getattr(m, "fwd_from", None),
    "only_forwards": lambda m, f: bool(getattr(m, "fwd_from", None)),
    "no_reply": lambda m, f: not getattr(m, "reply_to_msg_id", None),
    "only_reply": lambda m, f: bool(getattr(m, "reply_to_msg_id", None)),
    "mention": lambda m, f: bool(getattr(m, "mentioned", False)),
    "no_mention": lambda m, f: not getattr(m, "mentioned", False),
    "startswith": lambda m, f: (m.raw_text or "").startswith(f.startswith),
    "endswith": lambda m, f: (m.raw_text or "").endswith(f.endswith),
    "contains": lambda m, f: f.contains in (m.raw_text or ""),
    "regex": lambda m, f: bool(re.search(f.regex, m.raw_text or "")),
    "filter": lambda m, f: callable(f.filter) and bool(f.filter(m)),
    "from_id": lambda m, f: getattr(m, "sender_id", None) == f.from_id,
    "chat_id": lambda m, f: _chat_matches(m, f.chat_id),
    "no_commands": lambda m, f: not _is_command(m),
    "only_commands": lambda m, f: _is_command(m),
}


def _tag_filter(func: Any) -> Any:
    tags = [name for name in _TAGS if getattr(func, name, None) not in (None, False)]
    if not tags:
        return None

    def check(message: Any) -> bool:
        return all(_TAGS[name](message, func) for name in tags)

    return check


# --- конфиг ---


_MISSING = object()
_background: set[asyncio.Future] = set()  # on_change-корутины, чтобы их не собрал GC


class _ValidatorDoc:
    """Валидатор Hikka для ``.cfg`` Uroboros: подсказка — строкой."""

    def __init__(self, validator: Any):
        self.validator = validator
        self.doc = validators.doc_of(validator)

    def __call__(self, value: Any) -> Any:
        return self.validator.validate(value)


class ConfigValue(core.ConfigValue):
    def __init__(
        self,
        option: str,
        default: Any = None,
        doc: Any = "",
        value: Any = _MISSING,
        validator: Any = None,
        on_change: Any = None,
    ):
        super().__init__(option, default, "", _ValidatorDoc(validator) if validator is not None else None)
        self._doc = doc
        self.option = option
        self.on_change = on_change
        self.hikka_validator = validator

    @property
    def doc(self) -> str:
        doc = self._doc
        if callable(doc):
            try:
                doc = doc()
            except TypeError:
                doc = doc(None)  # FTG: lambda m: self.strings("...", m)
            except Exception:
                doc = ""
        return str(doc or "")

    @doc.setter
    def doc(self, value: Any) -> None:
        self._doc = value

    def validate(self, value: Any) -> Any:
        if isinstance(value, str):
            with contextlib.suppress(Exception):
                value = ast.literal_eval(value)
        if isinstance(value, (set, tuple)):
            value = list(value)
        if isinstance(value, list):
            value = [item.strip() if isinstance(item, str) else item for item in value]
        if self.hikka_validator is not None and value is not None:
            return self.hikka_validator.validate(value)
        return value


class ModuleConfig(core.ModuleConfig):
    def __init__(self, *entries: Any):
        if entries and not all(isinstance(entry, core.ConfigValue) for entry in entries):
            # Старый формат FTG: ключ, значение по умолчанию, описание, ключ, ...
            entries = tuple(
                ConfigValue(
                    entries[i],
                    entries[i + 1] if i + 1 < len(entries) else None,
                    entries[i + 2] if i + 2 < len(entries) else "",
                )
                for i in range(0, len(entries), 3)
            )
        super().__init__(*entries)

    def __getitem__(self, key: str) -> Any:
        if key not in self:
            return None
        return super().__getitem__(key)

    def __setitem__(self, key: str, value: Any) -> None:
        super().__setitem__(key, value)
        callback = getattr(self.value(key), "on_change", None)
        if callable(callback):
            result = callback()
            if inspect.isawaitable(result):
                task = asyncio.ensure_future(result)
                _background.add(task)
                task.add_done_callback(_background.discard)

    def get(self, key: str, default: Any = None) -> Any:
        return self[key] if key in self else default  # noqa: SIM401 — это и есть get

    def keys(self):
        return list(self)

    def values(self):
        return [self[key] for key in self]

    def items(self):
        return [(key, self[key]) for key in self]

    def getdoc(self, key: str, message: Any = None) -> str:
        return self.value(key).doc

    def getdef(self, key: str) -> Any:
        return self.value(key).default

    def set_no_raise(self, key: str, value: Any) -> None:
        with contextlib.suppress(validators.ValidationError):
            self[key] = value

    def change_validator(self, key: str, validator: Any) -> None:
        value = self.value(key)
        value.hikka_validator = validator
        value.validator = _ValidatorDoc(validator)

    def reload(self) -> None:
        pass


LibraryConfig = ModuleConfig


# --- окружение модуля: БД и список модулей в стиле Hikka ---


class HikkaDB:
    """БД в стиле Hikka: ``db.get(владелец, ключ, по_умолчанию)``."""

    def __init__(self, db: Any):
        self._db = db

    def get(self, owner: str, key: str, default: Any = None) -> Any:
        if (owner, key) == ("hikka.main", "command_prefix"):
            from ..utils import get_prefix

            return get_prefix(self._db)
        return self._db.get(owner, key, default)

    def set(self, owner: str, key: str, value: Any) -> bool:
        self._db.set(owner, key, value)
        return True

    def pointer(self, owner: str, key: str, default: Any = None, item_type: Any = None) -> Any:
        return self.get(owner, key, default)

    def save(self) -> bool:
        return True

    def __getitem__(self, owner: str) -> dict:
        return {key: self._db.get(owner, key) for key in self._db.keys(owner)}

    def __contains__(self, owner: str) -> bool:
        return bool(self._db.keys(owner))


class Modules:
    """``self.allmodules``: что Hikka-модули обычно спрашивают у загрузчика."""

    def __init__(self, loader: Any):
        self._loader = loader

    @property
    def modules(self) -> list:
        return list(self._loader.modules.values())

    @property
    def commands(self) -> dict:
        return {name: cmd.func for name, cmd in self._loader.commands.items()}

    @property
    def aliases(self) -> dict:
        from ..database import MAIN_OWNER

        return self._loader.db.get(MAIN_OWNER, "aliases", {})

    @property
    def inline_handlers(self) -> dict:
        return {name: handler.func for name, handler in self._loader.inline_handlers.items()}

    @property
    def callback_handlers(self) -> dict:
        return {f"{h.module.name}.{h.func.__name__}": h.func for h in self._loader.callback_handlers}

    @property
    def watchers(self) -> list:
        return [w.func for w in self._loader.watchers]

    @property
    def client(self) -> Any:
        return self._loader.client

    @property
    def db(self) -> HikkaDB:
        return HikkaDB(self._loader.db)

    @property
    def tg_id(self) -> int | None:
        return self._loader.security.me_id

    def lookup(self, name: str) -> Any:
        module = self._loader.get_module(name)
        if module is not None:
            return module
        lowered = name.lower()
        return next((m for m in self._loader.modules.values() if type(m).__name__.lower() == lowered), None)

    def get_classname(self, name: str) -> str | None:
        module = self.lookup(name)
        return type(module).__name__ if module else None

    def get_prefix(self, *_: Any) -> str:
        from ..utils import get_prefix

        return get_prefix(self._loader.db)

    def dispatch(self, command: str) -> tuple[str, Any]:
        found = self._loader.get_command(command)
        return command, found.func if found else None

    async def unload_module(self, classname: str) -> list[str]:
        removed = await self._loader.uninstall(classname)
        return [module.name for module in removed]

    def __getattr__(self, name: str) -> Any:
        raise AttributeError(f"allmodules.{name} из Hikka не поддерживается Uroboros")


class Strings(core.Strings):
    """Строки Hikka: ``self.strings("key")`` — без подстановки, лишние аргументы игнорируются."""

    def __call__(self, key: str, *_: Any, **kwargs: Any) -> str:
        return super().__call__(key, **kwargs) if kwargs else self[key]

    def __missing__(self, key: str) -> str:
        return f"Unknown strings: {key}"


async def _call_flexible(func: Any, *args: Any) -> Any:
    """Вызов ``client_ready(client, db)`` / ``client_ready()`` — в Hikka встречаются оба вида."""
    try:
        params = inspect.signature(func).parameters.values()
    except (TypeError, ValueError):
        params = []
    if any(p.kind == p.VAR_POSITIONAL for p in params):
        count = len(args)
    else:
        count = len([p for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)])
    result = func(*args[:count])
    if inspect.isawaitable(result):
        result = await result
    return result


def _bind_common(obj: Any, loader: Any) -> None:
    from . import aliases

    aliases.install()
    state.loader = loader
    obj.allmodules = Modules(loader)
    obj.db = obj._db = HikkaDB(loader.db)
    obj._client = obj.client
    obj.lookup = obj.allmodules.lookup
    obj.get_prefix = obj.allmodules.get_prefix
    obj.tg_id = obj._tg_id = loader.security.me_id
    obj.allclients = [obj.client]
    obj.inline = HikkaInline(obj.inline)
    if obj.client is not None:
        with contextlib.suppress(Exception):
            obj.client.tg_id = loader.security.me_id
            obj.client.loader = obj.allmodules


class Module(core.Module):
    """``loader.Module`` из Hikka."""

    strings = {"name": "Unknown"}  # noqa: RUF012 — как в Hikka

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        _prepare(cls)

    def _bind(self, loader: Any) -> None:
        _bind_common(self, loader)
        self.strings = Strings(self.strings)
        if isinstance(self.config, ModuleConfig):
            with contextlib.suppress(Exception):
                self.config_complete()
        for name in dir(type(self)):
            func = getattr(type(self), name, None)
            if getattr(func, "is_raw_handler", False) and self.client is not None:
                from telethon import events

                self.client.add_event_handler(getattr(self, name), events.Raw(types=list(func.updates) or None))

    def get(self, key: str, default: Any = None) -> Any:
        return self._db.get(type(self).__name__, key, default)

    def set(self, key: str, value: Any) -> bool:
        self._db.set(type(self).__name__, key, value)
        return True

    def pointer(self, key: str, default: Any = None, item_type: Any = None) -> Any:
        return self.get(key, default)

    def config_complete(self) -> None:
        """Вызывается, когда конфиг модуля готов."""

    async def client_ready(self, *args: Any) -> None:
        """Вызывается после загрузки модуля."""

    async def on_load(self) -> None:
        await _call_flexible(self.client_ready, self.client, self._db)

    async def import_lib(self, url: str, *, reload: bool = False, **_: Any) -> Any:
        return await super().import_lib(url, reload=reload)

    async def animate(self, message: Any, frames: list[str], interval: float, *, inline: bool = False) -> Any:
        """Показывает кадры по очереди, редактируя сообщение."""
        interval = max(interval, 0.1)
        for frame in frames:
            message = await utils.answer(message, frame)
            await asyncio.sleep(interval)
        return message

    async def request_join(self, peer: Any, reason: str, assure_joined: bool = False) -> bool:
        # Hikka предлагает вступить в канал автора модуля; Uroboros этого не делает.
        log.info("Модуль %s просит вступить в %s: %s — пропущено", self.name, peer, reason)
        return False

    async def invoke(self, command: str, args: str | None = None, peer: Any = None, message: Any = None, edit=False):
        raise LoadError("self.invoke из Hikka не поддерживается Uroboros")


class Library(core.Library):
    """``loader.Library`` из Hikka."""

    strings = {"name": "Unknown"}  # noqa: RUF012 — как в Hikka

    def _bind(self, loader: Any) -> None:
        _bind_common(self, loader)
        self.strings = Strings(getattr(self, "strings", {}) or {})

    def _lib_get(self, key: str, default: Any = None) -> Any:
        return self._db.get(type(self).__name__, key, default)

    def _lib_set(self, key: str, value: Any) -> bool:
        self._db.set(type(self).__name__, key, value)
        return True

    get = _lib_get
    set = _lib_set

    async def on_load(self) -> None:
        init = getattr(self, "init", None)
        if callable(init):
            await _call_flexible(init)


# --- перевод меток Hikka в Uroboros при создании класса ---


def _strip_suffix(name: str, suffix: str) -> str:
    return name.rsplit(suffix, 1)[0] if name.endswith(suffix) else name


def _wrap_inline_handler(func: Any) -> Any:
    @functools.wraps(func)
    async def handler(self: Any, query: Any) -> Any:
        return convert_inline_results(await func(self, HikkaInlineQuery(query)))

    return handler


def _wrap_callback_handler(func: Any) -> Any:
    @functools.wraps(func)
    async def handler(self: Any, call: Any) -> Any:
        return await func(self, HikkaCall(call))

    return handler


def _wrap_on_dlmod(func: Any) -> Any:
    @functools.wraps(func)
    async def on_dlmod(self: Any) -> None:
        # Как в Hikka: ошибка в on_dlmod не отменяет установку.
        try:
            await _call_flexible(functools.partial(func, self), self.client, self._db)
        except Exception:
            log.exception("Ошибка в on_dlmod модуля %s", self.name)

    return on_dlmod


def _prepare(cls: type) -> None:
    strings = {**getattr(cls, "strings", {}), **getattr(cls, "strings_ru", {})}
    cls.strings = strings
    name = strings.get("name")
    if not name or name == "Unknown":
        name = cls.__name__.removesuffix("Mod")
        strings["name"] = name
    cls.name = name
    if strings.get("_cls_doc"):
        cls.__doc__ = strings["_cls_doc"]

    if "on_dlmod" in cls.__dict__:
        cls.on_dlmod = _wrap_on_dlmod(cls.__dict__["on_dlmod"])

    for attr, value in list(cls.__dict__.items()):
        if isinstance(value, InfiniteLoop):
            func = value.func
            setattr(func, LOOP_ATTR, LoopInfo(float(value.interval), bool(value.autostart), bool(value.wait_before)))
            setattr(cls, attr, func)
            continue
        if attr.startswith("__") or not callable(value):
            continue

        if attr.endswith("cmd") or getattr(value, "is_command", False):
            cmd = _strip_suffix(attr, "cmd").lower()
            if not cmd:
                continue
            aliases = list(getattr(value, "aliases", None) or [])
            if getattr(value, "alias", None):
                aliases.append(value.alias)
            doc = getattr(value, "ru_doc", None) or strings.get(f"_cmd_doc_{cmd}") or inspect.getdoc(value) or ""
            setattr(
                value,
                COMMAND_ATTR,
                CommandInfo(
                    name=cmd,
                    aliases=tuple(alias.lower() for alias in aliases),
                    doc=doc.strip(),
                    filter=_tag_filter(value),
                    access=security.access_of(value),
                ),
            )
        elif attr.endswith("watcher") or getattr(value, "is_watcher", False):
            setattr(
                value,
                WATCHER_ATTR,
                WatcherInfo(
                    only_outgoing=bool(getattr(value, "out", False)),
                    only_incoming=bool(getattr(value, "in", False)),
                    filter=_tag_filter(value),
                ),
            )
        elif attr.endswith("_inline_handler") or getattr(value, "is_inline_handler", False):
            handler_name = _strip_suffix(attr, "_inline_handler").lower()
            doc = (
                getattr(value, "ru_doc", None)
                or strings.get(f"_ihandle_doc_{handler_name}")
                or inspect.getdoc(value)
                or ""
            )
            wrapped = _wrap_inline_handler(value)
            setattr(wrapped, INLINE_ATTR, InlineHandlerInfo(handler_name, doc.strip()))
            setattr(cls, attr, wrapped)
        elif attr.endswith("_callback_handler") or getattr(value, "is_callback_handler", False):
            wrapped = _wrap_callback_handler(value)
            setattr(wrapped, CALLBACK_ATTR, CallbackHandlerInfo(None))
            setattr(cls, attr, wrapped)


def __getattr__(name: str) -> Any:
    raise AttributeError(f"loader.{name} из Hikka не поддерживается Uroboros")
