"""Uroboros: модульный юзербот для Telegram."""

__version__ = "1.0.0"

from . import utils, validators
from .decorators import callback_handler, command, inline_handler, watcher
from .errors import InlineError, LoadError
from .loops import StopLoop, loop
from .types import ConfigValue, Library, Module, ModuleConfig

__all__ = [
    "ConfigValue",
    "InlineError",
    "Library",
    "LoadError",
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
