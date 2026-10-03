"""``from .. import main``: то немногое из ``hikka.main``, на что ссылаются модули."""

from __future__ import annotations

from .version import __version__

__all__ = ["__version__", "get_config_key"]

# Модули используют main.__name__ как владельца ключей БД (префикс и т.п.).
__name__ = "hikka.main"


def get_config_key(key: str):
    if key == "prefix":
        from ..utils import get_prefix
        from .state import get_loader

        return get_prefix(get_loader().db)
    return None
