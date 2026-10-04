"""Защита во время работы: сторонние модули не трогают сессию, секреты в ``data/`` и опасные запросы.

Это защита от типичного вредного кода, а не песочница: код в том же процессе при большом желании её обойдёт.
Модуль, опасный код которого пользователь явно подтвердил при установке, считается доверенным и не ограничивается
(список — БД ``uroboros.loader``/``trusted``).

Что проверяется:

- запросы к Telegram (``UroborosClient.__call__``): завершение сеансов, удаление аккаунта, смена пароля 2FA
  и номера, вход по QR, выход из аккаунта, траты звёзд и подарков;
- ``client.session`` (``UroborosClient.session``): читать сессию из кода стороннего модуля нельзя;
- файлы (audit hook Python): открыть, удалить, переименовать сессию, ``config.json`` и ``uroboros.db``,
  передать их пути в команду системы.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .database import LOADER_OWNER
from .errors import LoadError
from .ratelimit import current_module

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
MODULE_PACKAGES = ("uroboros.ext.", "uroboros.lib.", "uroboros.hikka.modules.")

_active: Guard | None = None
_hook_installed = False


class ModuleBlocked(LoadError, PermissionError):
    """Сторонний модуль попытался сделать то, что угрожает аккаунту."""


class Guard:
    def __init__(self, loader: Loader, data_dir: Path):
        self.loader = loader
        self.data_dir = Path(os.path.realpath(data_dir))
        self.secrets = tuple(str(self.data_dir / name) for name in SECRET_FILES)
        self.on_block = None  # функция(имя модуля, что пытался сделать): уведомить пользователя

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

    def block(self, module_name: str, action: str) -> ModuleBlocked:
        log.warning("Модулю %s заблокировано: %s", module_name, action)
        if self.on_block is not None:
            self.on_block(module_name, action)
        return ModuleBlocked(f"Модулю {module_name} нельзя {action}: это угрожает аккаунту")

    # --- запросы ---

    def check_request(self, request: Any) -> None:
        module = current_module.get()
        if not self.restricted(module):
            return
        for item in request if isinstance(request, list) else (request,):
            action = BLOCKED_REQUESTS.get(type(item).__name__)
            if action:
                raise self.block(module.name, action)

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
        count = FILE_EVENTS.get(event)
        is_process = count is None and event in PROCESS_EVENTS
        if count is None and not is_process:
            return
        module = current_module.get()
        if not self.restricted(module):
            return
        if is_process:
            text = " ".join(map(str, _flatten(args)))
            if str(self.data_dir) in text or any(name in text for name in SECRET_FILES):
                raise self.block(module.name, "передавать файлы сессии и настроек в команды системы")
            return
        if any(self.is_secret(path) for path in args[:count] if path is not None):
            raise self.block(module.name, "трогать файлы сессии, config.json и базу данных")


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
