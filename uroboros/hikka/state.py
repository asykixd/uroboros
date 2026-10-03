"""Общее состояние адаптера: загрузчик Uroboros, к которому привязаны модули Hikka."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..loader import Loader

loader: Loader | None = None


def get_loader() -> Loader:
    if loader is None:
        raise RuntimeError("Адаптер Hikka ещё не привязан к загрузчику")
    return loader
