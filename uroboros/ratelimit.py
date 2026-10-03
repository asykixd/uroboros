"""Защита от флуда API: сторонний модуль, который шлёт слишком много запросов, замораживается.

Чей запрос — определяет контекст: ядро выставляет ``current_module`` на время вызова команды,
вотчера, фоновой задачи, колбэка кнопки и хуков модуля. Задачи, которые модуль создаёт
внутри, наследуют контекст (так работает ``contextvars`` в asyncio).
"""

from __future__ import annotations

import contextlib
import contextvars
import logging
import time
from collections import deque
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from .errors import LoadError
from .security import SECURITY_OWNER

if TYPE_CHECKING:
    from .database import Database

log = logging.getLogger(__name__)

current_module: contextvars.ContextVar[Any] = contextvars.ContextVar("uroboros_module", default=None)

DEFAULTS = {"limit": 60, "window": 30, "freeze": 300, "enabled": True}


class ModuleFrozen(LoadError):
    """Модуль заморожен за флуд запросами."""


@contextlib.contextmanager
def module_context(module: Any) -> Iterator[None]:
    """Запросы внутри блока считаются запросами модуля ``module``."""
    token = current_module.set(module)
    try:
        yield
    finally:
        current_module.reset(token)


def format_seconds(seconds: float) -> str:
    seconds = max(1, round(seconds))
    return f"{seconds // 60} мин {seconds % 60} с" if seconds >= 60 else f"{seconds} с"


class RateLimiter:
    def __init__(self, db: Database, clock=time.monotonic):
        self.db = db
        self.clock = clock
        self._requests: dict[str, deque[float]] = {}
        self.frozen: dict[str, float] = {}  # имя модуля → до какого момента (по clock)
        self.on_freeze = None  # async-функция(name, seconds): уведомить пользователя

    @property
    def settings(self) -> dict[str, Any]:
        return {**DEFAULTS, **self.db.get(SECURITY_OWNER, "flood", {})}

    def configure(self, **values: Any) -> None:
        self.db.set(SECURITY_OWNER, "flood", {**self.db.get(SECURITY_OWNER, "flood", {}), **values})

    def frozen_for(self, name: str) -> float:
        """Сколько секунд модулю ещё сидеть замороженным; 0 — не заморожен."""
        until = self.frozen.get(name)
        if until is None:
            return 0
        left = until - self.clock()
        if left <= 0:
            del self.frozen[name]
            return 0
        return left

    def unfreeze(self, name: str) -> bool:
        self._requests.pop(name, None)
        return self.frozen.pop(name, None) is not None

    def check(self, module: Any, count: int = 1) -> None:
        """Учитывает ``count`` запросов модуля. Бросает ``ModuleFrozen``, если лимит превышен."""
        if getattr(module, "is_builtin", True):
            return
        settings = self.settings
        if not settings["enabled"]:
            return
        name = module.name
        left = self.frozen_for(name)
        if left:
            raise ModuleFrozen(f"Модуль {name} заморожен за флуд запросами ещё на {format_seconds(left)}")

        now = self.clock()
        requests = self._requests.setdefault(name, deque())
        while requests and requests[0] <= now - settings["window"]:
            requests.popleft()
        requests.extend([now] * count)
        if len(requests) <= settings["limit"]:
            return

        requests.clear()
        self.frozen[name] = now + settings["freeze"]
        log.warning(
            "Модуль %s заморожен на %d с: больше %d запросов за %d с",
            name,
            settings["freeze"],
            settings["limit"],
            settings["window"],
        )
        if self.on_freeze is not None:
            self.on_freeze(name, settings)
        raise ModuleFrozen(
            f"Модуль {name} заморожен на {format_seconds(settings['freeze'])}: "
            f"больше {settings['limit']} запросов за {settings['window']} с"
        )
