"""Устаревание публичного API: предупреждение, а не поломка.

Устаревшее имя работает ещё минимум одну минорную версию и удаляется не раньше следующей
мажорной. При использовании — ``DeprecationWarning`` и одно предупреждение в лог на имя.
"""

from __future__ import annotations

import functools
import logging
import warnings
from collections.abc import Callable
from typing import Any, TypeVar

log = logging.getLogger("uroboros.deprecation")

F = TypeVar("F", bound=Callable[..., Any])
_reported: set[str] = set()


def warn(name: str, *, since: str, removed_in: str, alternative: str | None = None, stacklevel: int = 3) -> None:
    text = f"{name} устарело с версии {since} и будет удалено в {removed_in}"
    if alternative:
        text += f": используйте {alternative}"
    warnings.warn(text, DeprecationWarning, stacklevel=stacklevel)
    if name not in _reported:
        _reported.add(name)
        log.warning(text)


def deprecated(*, since: str, removed_in: str, alternative: str | None = None) -> Callable[[F], F]:
    """Помечает функцию или метод устаревшими."""

    def decorator(func: F) -> F:
        name = getattr(func, "__qualname__", repr(func))

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            warn(name, since=since, removed_in=removed_in, alternative=alternative)
            return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
