"""Декораторы для методов модуля: команды и вотчеры."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

COMMAND_ATTR = "_uroboros_command"
WATCHER_ATTR = "_uroboros_watcher"


@dataclass(frozen=True)
class CommandInfo:
    name: str
    aliases: tuple[str, ...]
    doc: str


@dataclass(frozen=True)
class WatcherInfo:
    only_outgoing: bool
    only_incoming: bool
    filter: Callable[[Any], bool] | None


def command(
    name: str | None = None,
    *,
    aliases: list[str] | tuple[str, ...] = (),
    doc: str | None = None,
):
    """Помечает метод как команду ``<префикс><name>``.

    Без имени берётся имя метода (суффикс ``cmd`` отбрасывается).
    Описание — ``doc`` или докстринг метода.
    """

    def decorator(func):
        cmd_name = (name or func.__name__.removesuffix("cmd")).lower()
        setattr(
            func,
            COMMAND_ATTR,
            CommandInfo(
                name=cmd_name,
                aliases=tuple(alias.lower() for alias in aliases),
                doc=(doc or func.__doc__ or "").strip(),
            ),
        )
        return func

    return decorator


def watcher(
    *,
    only_outgoing: bool = False,
    only_incoming: bool = False,
    filter: Callable[[Any], bool] | None = None,
):
    """Помечает метод как обработчик всех новых сообщений."""

    def decorator(func):
        setattr(func, WATCHER_ATTR, WatcherInfo(only_outgoing, only_incoming, filter))
        return func

    return decorator
