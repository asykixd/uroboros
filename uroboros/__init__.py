"""Uroboros: модульный юзербот для Telegram."""

__version__ = "0.1.0b1"

from . import utils, validators
from .decorators import command, watcher
from .types import ConfigValue, Module, ModuleConfig

__all__ = [
    "__version__",
    "ConfigValue",
    "Module",
    "ModuleConfig",
    "command",
    "utils",
    "validators",
    "watcher",
]
