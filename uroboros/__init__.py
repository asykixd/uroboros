"""Uroboros: модульный юзербот для Telegram."""

__version__ = "0.1.1b2"

from . import utils, validators
from .decorators import command, watcher
from .loops import loop
from .types import ConfigValue, Library, Module, ModuleConfig

__all__ = [
    "ConfigValue",
    "Library",
    "Module",
    "ModuleConfig",
    "__version__",
    "command",
    "loop",
    "utils",
    "validators",
    "watcher",
]
