"""Защита во время работы: сторонние модули не трогают сессию, секреты в ``data/`` и опасные запросы.

Это защита от типичного вредного кода, а не песочница: код в том же процессе при большом желании её обойдёт.
Модуль, опасный код которого пользователь явно подтвердил при установке, считается доверенным и не ограничивается
(список — БД ``uroboros.loader``/``trusted``).

Что проверяется:

- запросы к Telegram (``UroborosClient.__call__``): завершение сеансов, удаление аккаунта, смена пароля 2FA
  и номера, вход по QR, выход из аккаунта, траты звёзд и подарков;
- ``client.session`` (``UroborosClient.session``): читать сессию из кода стороннего модуля нельзя;
- БД (``Database``): менять системные настройки (``uroboros.*``: права доступа, доверенные модули, токен бота)
  и читать токен inline-бота;
- файлы (audit hook Python): открыть, удалить, переименовать сессию, ``config.json`` и ``uroboros.db``,
  передать их пути в команду системы;
- declared permissions (``# meta permissions``): a module with the header may use only the network, files and
  processes it declared. Modules without the header are not limited this way.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import sys
import time
from collections.abc import Callable
from pathlib import Path
from types import FrameType
from typing import TYPE_CHECKING, Any

from .database import LOADER_OWNER
from .errors import LoadError
from .ratelimit import current_module, module_context
from .security import SECURITY_OWNER

if TYPE_CHECKING:
    from .loader import Loader

log = logging.getLogger(__name__)

BLOCKED_REQUESTS = {
    "ResetAuthorizationsRequest": "завершить все другие сеансы аккаунта",
    "ResetAuthorizationRequest": "завершить сеанс аккаунта",
    "DeleteAccountRequest": "удалить аккаунт",
    "UpdatePasswordSettingsRequest": "изменить пароль 2FA",
    "ResetPasswordRequest": "сбросить пароль 2FA",
    "ChangePhoneRequest": "изменить номер телефона",
    "SendChangePhoneCodeRequest": "изменить номер телефона",
    "ExportLoginTokenRequest": "войти в аккаунт по QR-коду",
    "ImportLoginTokenRequest": "войти в аккаунт по QR-коду",
    "AcceptLoginTokenRequest": "подтвердить вход с другого устройства",
    "LogOutRequest": "выйти из аккаунта",
    "SendStarsFormRequest": "потратить звёзды",
    "SendPaymentFormRequest": "совершить платёж",
    "TransferStarGiftRequest": "передать подарок",
}
SECRET_FILES = ("uroboros.session", "config.json", "uroboros.db")  # с суффиксами -journal, -wal, -shm
FILE_EVENTS = {
    "open": 1,  # сколько первых аргументов — пути
    "os.remove": 1,
    "os.rmdir": 1,
    "os.rename": 2,
    "os.truncate": 1,
    "os.chmod": 1,
    "os.link": 2,
    "os.symlink": 2,
    "shutil.copyfile": 2,
    "shutil.rmtree": 1,
    "sqlite3.connect": 1,
}
PROCESS_EVENTS = {"os.system", "subprocess.Popen", "os.exec", "os.posix_spawn", "os.spawn"}
SECRET_KEYS = {("uroboros.inline", "token")}
BLOCKS_KEY = "blocks"  # in uroboros.security: the last BLOCKS_LIMIT blocks, for .security log
BLOCKS_LIMIT = 100
MODULE_PACKAGES = ("uroboros.ext.", "uroboros.lib.", "uroboros.hikka.modules.")

# Declared permissions (# meta permissions) enforced at runtime. "env" and "exec" have no reliable audit events
# (and the standard library itself runs exec), so they are only checked by the install-time scan.
ENFORCED_PERMISSIONS = {
    "network": "выходить в сеть",
    "files": "работать с файлами",
    "processes": "запускать команды в системе",
}
EVENT_PERMISSIONS = {
    **dict.fromkeys(("socket.connect", "socket.sendto", "socket.sendmsg", "socket.bind"), "network"),
    **dict.fromkeys((*FILE_EVENTS, "os.mkdir", "os.listdir", "os.scandir"), "files"),
    **dict.fromkeys((*PROCESS_EVENTS, "os.fork", "os.forkpty"), "processes"),
}
READ_EVENTS = {"os.listdir", "os.scandir"}
# Who caused an event: the nearest frame of module code or of code that acts on its own behalf (the core, Telethon
# talking to Telegram, imports). Libraries in between act for their caller. Frames of these packages act for the
# module that called them, so they never count as the core.
OWN_CODE = ("uroboros.ext.", "uroboros.hikka.modules.")
PASS_THROUGH = ("uroboros.lib.", "uroboros.hikka.modules.lib_", "uroboros.utils", "uroboros.hikka.utils")
CORE_CODE = {
    "network": ("uroboros.", "telethon.", "aiogram."),
    "files": ("uroboros.", "aiogram.", "importlib", "zipimport", "linecache", "logging", "mimetypes"),
    "processes": ("uroboros.",),
}
# An event no frame can be attributed to (library tasks, threads): network is let through, because aiohttp opens
# connections for the inline bot in tasks of its own; files and processes are blocked.
UNATTRIBUTED_BLOCKED = {"files", "processes"}


def _python_roots() -> tuple[str, ...]:
    """Python's own files (stdlib, site-packages, time zones): reading them is not file access of a module."""
    import sysconfig
    import zoneinfo

    paths = {sys.prefix, sys.base_prefix, sys.exec_prefix, *zoneinfo.TZPATH}
    paths |= {sysconfig.get_path(name) for name in ("stdlib", "platstdlib", "purelib", "platlib")}
    return tuple(os.path.join(os.path.realpath(p), "") for p in paths if p)


_active: Guard | None = None
_hook_installed = False


class ModuleBlocked(LoadError, PermissionError):
    """Сторонний модуль попытался сделать то, что угрожает аккаунту."""


class Guard:
    def __init__(self, loader: Loader, data_dir: Path):
        self.loader = loader
        self.data_dir = Path(os.path.realpath(data_dir))
        self.secrets = tuple(str(self.data_dir / name) for name in SECRET_FILES)
        # функция(имя модуля, что пытался сделать): уведомить пользователя
        self.on_block: Callable[[str, str], object] | None = None
        self.python_roots = _python_roots()
        loader.db._check = self.check_db

    # --- доверенные модули ---

    def trusted(self) -> set[str]:
        return set(self.loader.db.get(LOADER_OWNER, "trusted", []))

    def set_trusted(self, stem: str, trusted: bool) -> None:
        stems = self.trusted()
        (stems.add if trusted else stems.discard)(stem)
        self.loader.db.set(LOADER_OWNER, "trusted", sorted(stems))

    def restricted(self, module: Any) -> bool:
        return (
            module is not None
            and not getattr(module, "is_builtin", True)
            and getattr(module, "_stem", None) not in self.trusted()
        )

    def block(self, module_name: str, action: str, reason: str = "это угрожает аккаунту") -> ModuleBlocked:
        log.warning("Модулю %s заблокировано: %s", module_name, action)
        self._record(module_name, action)
        if self.on_block is not None:
            self.on_block(module_name, action)
        return ModuleBlocked(f"Модулю {module_name} нельзя {action}: {reason}")

    # --- журнал ---

    def blocks(self) -> list[dict[str, Any]]:
        """Recent blocks, oldest first: ``{"time": unix time, "module": name, "action": text}``."""
        return self.loader.db.get(SECURITY_OWNER, BLOCKS_KEY, [])

    def clear_blocks(self) -> None:
        self.loader.db.delete(SECURITY_OWNER, BLOCKS_KEY)

    def _record(self, module_name: str, action: str) -> None:
        entry = {"time": int(time.time()), "module": module_name, "action": action}
        try:
            # The core writes the log on the module's behalf: the DB guard would otherwise block this very write.
            with module_context(None):
                self.loader.db.set(SECURITY_OWNER, BLOCKS_KEY, [*self.blocks(), entry][-BLOCKS_LIMIT:])
        except (sqlite3.Error, ValueError):
            # e.g. a block in another thread: the connection belongs to the event loop thread; the log line is enough
            log.exception("Не удалось записать блокировку модуля %s в журнал", module_name)

    # --- запросы ---

    def check_request(self, request: Any) -> None:
        module = current_module.get()
        if not self.restricted(module):
            return
        for item in request if isinstance(request, list) else (request,):
            action = BLOCKED_REQUESTS.get(type(item).__name__)
            if action:
                raise self.block(module.name, action)

    # --- БД ---

    def check_db(self, action: str, owner: str, key: str | None) -> None:
        """``key`` None — вся БД сразу (``dump``, ``replace_all``)."""
        if action == "get" and key is not None and (owner, key) not in SECRET_KEYS:
            return
        module = current_module.get()
        if not self.restricted(module):
            return
        if action == "get":
            raise self.block(module.name, "читать токен inline-бота и всю базу данных")
        raise self.block(module.name, f"менять системные настройки Uroboros ({owner.rstrip('.')})")

    # --- сессия ---

    def check_session_access(self, caller: str) -> None:
        """``caller`` — ``__name__`` кода, который читает ``client.session``."""
        if not caller.startswith(MODULE_PACKAGES):
            return
        module = self._module_by_package(caller)
        if module is None or self.restricted(module):
            raise self.block(module.name if module else caller, "читать сессию клиента")

    def _module_by_package(self, name: str) -> Any:
        for module in self.loader.modules.values():
            if type(module).__module__ == name:
                return module
        return None

    # --- файлы ---

    def is_secret(self, path: Any) -> bool:
        if isinstance(path, int):
            return False  # дескриптор уже открытого файла
        try:
            real = os.path.realpath(os.fsdecode(path))
        except (TypeError, ValueError):
            return False
        return real.startswith(self.secrets)

    def audit(self, event: str, args: tuple) -> None:
        permission = EVENT_PERMISSIONS.get(event)
        if permission is None:
            return
        module = current_module.get()
        if not self.restricted(module):
            return
        count = FILE_EVENTS.get(event)
        if event in PROCESS_EVENTS:
            text = " ".join(map(str, _flatten(args)))
            if str(self.data_dir) in text or any(name in text for name in SECRET_FILES):
                raise self.block(module.name, "передавать файлы сессии и настроек в команды системы")
        elif count is not None and any(self.is_secret(path) for path in args[:count] if path is not None):
            raise self.block(module.name, "трогать файлы сессии, config.json и базу данных")
        self.check_permission(module, permission, event, args)

    # --- объявленные права ---

    def check_permission(self, module: Any, permission: str, event: str, args: tuple) -> None:
        """A module that declared its permissions may use only those (modules without the header: anything)."""
        declared = getattr(module, "_permissions", None)
        if declared is None or permission in declared:
            return
        if permission == "files" and not self._file_access(event, args):
            return
        if not _caused_by_module(permission):
            return
        raise self.block(
            module.name,
            ENFORCED_PERMISSIONS[permission],
            f"право {permission} не объявлено в # meta permissions",
        )

    def _file_access(self, event: str, args: tuple) -> bool:
        """False for what isn't the module's own file access: open descriptors, in-memory DBs, reading Python."""
        path = args[0] if args else None
        if isinstance(path, int) or path in (None, "", ":memory:", b""):
            return False
        if not _writes(event, args):
            try:
                real = os.path.realpath(os.fsdecode(path))
            except (TypeError, ValueError):
                return True
            if real.startswith(self.python_roots):
                return False
        return True


def _writes(event: str, args: tuple) -> bool:
    if event in READ_EVENTS:
        return False
    if event != "open":
        return True
    mode = args[1] if len(args) > 1 else None
    if isinstance(mode, str):
        return any(char in mode for char in "wax+")
    flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
    return bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))


def _caused_by_module(permission: str) -> bool:
    """Walks the stack from the event outwards to the first frame that owns the action."""
    core = CORE_CODE[permission]
    frame: FrameType | None = sys._getframe(1)
    while frame is not None:
        name = frame.f_globals.get("__name__") or ""
        if name != __name__ and not name.startswith(PASS_THROUGH):
            if name.startswith(OWN_CODE):
                return True
            if name.startswith(core):
                return False
        frame = frame.f_back
    return permission in UNATTRIBUTED_BLOCKED


def _flatten(args: Any) -> list[Any]:
    found = []
    for arg in args:
        if isinstance(arg, (list, tuple)):
            found += _flatten(arg)
        elif isinstance(arg, (str, bytes, os.PathLike)):
            found.append(os.fsdecode(arg))
    return found


def _hook(event: str, args: tuple) -> None:
    guard = _active
    if guard is not None:
        guard.audit(event, args)


def activate(guard: Guard | None) -> None:
    """Включает проверку файлов для ``guard`` (None — выключить). Audit hook ставится один раз на процесс."""
    global _active, _hook_installed
    _active = guard
    if guard is not None and not _hook_installed:
        sys.addaudithook(_hook)
        _hook_installed = True
