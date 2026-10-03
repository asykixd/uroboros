"""``from ..types import ...``: типы Hikka, на которые ссылаются модули."""

from .inline_adapter import HikkaInlineMessage as InlineMessage
from .loader import (
    ConfigValue,
    CoreOverwriteError,
    CoreUnloadError,
    Library,
    LibraryConfig,
    LoadError,
    Module,
    ModuleConfig,
    SelfSuspend,
    SelfUnload,
    StopLoop,
)

JSONSerializable = dict | list | str | int | float | bool | None

__all__ = [
    "ConfigValue",
    "CoreOverwriteError",
    "CoreUnloadError",
    "InlineMessage",
    "JSONSerializable",
    "Library",
    "LibraryConfig",
    "LoadError",
    "Module",
    "ModuleConfig",
    "SelfSuspend",
    "SelfUnload",
    "StopLoop",
]
