"""Фоновые задачи модулей: ``@loop``."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .ratelimit import ModuleFrozen, module_context

log = logging.getLogger(__name__)

LOOP_ATTR = "_uroboros_loop"


@dataclass(frozen=True)
class LoopInfo:
    interval: float
    autostart: bool
    wait_before: bool


def loop(interval: float, *, autostart: bool = True, wait_before: bool = False):
    """Помечает метод как фоновую задачу, которая вызывается каждые ``interval`` секунд.

    После загрузки модуля ``self.<метод>`` — это объект :class:`Loop` с ``start()``,
    ``stop()`` и ``running``. ``autostart`` запускает задачу сразу после ``on_load``,
    ``wait_before`` — ждать интервал перед первым вызовом. При выгрузке модуля задача
    останавливается сама. Ошибка в одном вызове логируется и не останавливает цикл.
    """
    if interval <= 0:
        raise ValueError("interval должен быть больше нуля")

    def decorator(func):
        setattr(func, LOOP_ATTR, LoopInfo(float(interval), autostart, wait_before))
        return func

    return decorator


class Loop:
    def __init__(self, func: Callable[[], Awaitable[Any]], info: LoopInfo, module: Any):
        self.func = func
        self.info = info
        self.interval = info.interval
        self.module = module
        self.module_name = getattr(module, "name", str(module))
        self._task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self, interval: float | None = None) -> None:
        """Запускает задачу (если уже идёт — только меняет интервал)."""
        if interval is not None:
            if interval <= 0:
                raise ValueError("interval должен быть больше нуля")
            self.interval = interval
        if not self.running:
            self._task = asyncio.get_running_loop().create_task(self._run())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()

    async def wait_stopped(self) -> None:
        """Останавливает задачу и дожидается её завершения."""
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def __call__(self) -> Any:
        """Один вызов вне расписания."""
        return await self.func()

    async def _run(self) -> None:
        if self.info.wait_before:
            await asyncio.sleep(self.interval)
        while True:
            try:
                with module_context(self.module):
                    await self.func()
            except ModuleFrozen:
                pass  # о заморозке уже сообщили; задача продолжит после разморозки
            except Exception:
                log.exception("Ошибка в фоновой задаче %s.%s", self.module_name, self.func.__name__)
            await asyncio.sleep(self.interval)
