"""Uroboros: модульный юзербот для Telegram."""

__version__ = "0.2.0-dev"

from . import utils, validators
from .decorators import callback_handler, command, inline_handler, watcher
from .loops import loop
from .types import ConfigValue, Library, Module, ModuleConfig

__all__ = [
    "ConfigValue",
    "Library",
    "Module",
    "ModuleConfig",
    "__version__",
    "callback_handler",
    "command",
    "inline_handler",
    "loop",
    "utils",
    "validators",
    "watcher",
]
