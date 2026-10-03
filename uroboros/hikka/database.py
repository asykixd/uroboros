"""``from ..database import Database``: БД в стиле Hikka (обычно нужна модулям только для аннотаций)."""

from .loader import HikkaDB as Database


class PointerList(list):
    """В Hikka — список, который сам сохраняется в БД. Здесь — обычный список: сохраняйте через ``set``."""


class PointerDict(dict):
    """В Hikka — словарь, который сам сохраняется в БД. Здесь — обычный словарь: сохраняйте через ``set``."""


__all__ = ["Database", "PointerDict", "PointerList"]
