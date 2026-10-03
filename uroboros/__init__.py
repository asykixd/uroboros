"""Uroboros: модульный юзербот для Telegram."""

__version__ = "0.3.0-dev"

from . import utils, validators
from .decorators import callback_handler, command, inline_handler, watcher
from .loops import StopLoop, loop
from .types import ConfigValue, Library, Module, ModuleConfig

__all__ = [
    "ConfigValue",
    "Library",
    "Module",
    "ModuleConfig",
    "StopLoop",
    "__version__",
    "callback_handler",
    "command",
    "inline_handler",
    "loop",
    "utils",
    "validators",
    "watcher",
]
