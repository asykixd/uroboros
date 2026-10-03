"""``import hikkatl...`` (форк Telethon из Hikka) и ``herokutl...`` (из Heroku) → обычный Telethon.

Уже загруженные подмодули Telethon регистрируются под вторым именем как есть (тот же объект).
Остальные подгружает finder: он импортирует настоящий подмодуль и отдаёт его копию под
именем ``hikkatl...`` — классы в ней те же, так что ``isinstance`` работает.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import sys
from types import ModuleType

ALIASES = {"hikkatl": "telethon", "herokutl": "telethon"}


def _real_name(fullname: str) -> str | None:
    top, _, rest = fullname.partition(".")
    real = ALIASES.get(top)
    if real is None:
        return None
    return f"{real}.{rest}" if rest else real


class _AliasLoader(importlib.abc.Loader):
    def __init__(self, real: str):
        self.real = real

    def create_module(self, spec):
        real = importlib.import_module(self.real)
        module = ModuleType(spec.name)
        module.__dict__.update({k: v for k, v in vars(real).items() if k not in ("__spec__", "__loader__", "__name__")})
        if hasattr(real, "__path__"):
            module.__path__ = []  # пакет: подмодули тоже найдёт этот finder
        return module

    def exec_module(self, module):
        pass


class _AliasFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        real = _real_name(fullname)
        if real is None:
            return None
        if real in sys.modules:
            # Тот же объект, без новой спецификации: настоящему модулю ничего не меняем.
            sys.modules[fullname] = sys.modules[real]
            return importlib.util.spec_from_loader(fullname, _Existing(sys.modules[real]))
        if importlib.util.find_spec(real) is None:
            return None
        return importlib.util.spec_from_loader(fullname, _AliasLoader(real), is_package=True)


class _Existing(importlib.abc.Loader):
    """Модуль уже есть в ``sys.modules`` под вторым именем: вернуть его, ничего не исполняя."""

    def __init__(self, module: ModuleType):
        self.module = module

    def create_module(self, spec):
        return _Proxy(self.module, spec.name)

    def exec_module(self, module):
        sys.modules[module.__name__] = self.module


class _Proxy(ModuleType):
    def __init__(self, real: ModuleType, name: str):
        super().__init__(name)
        self.__dict__.update({k: v for k, v in vars(real).items() if k not in ("__spec__", "__loader__", "__name__")})


_installed = False


def install() -> None:
    """Регистрирует уже загруженный Telethon под именем ``hikkatl`` и ставит finder для остального."""
    global _installed
    for alias, real in ALIASES.items():
        importlib.import_module(real)
        for name, module in list(sys.modules.items()):
            if name == real or name.startswith(real + "."):
                sys.modules.setdefault(alias + name[len(real) :], module)
    if not _installed:
        sys.meta_path.append(_AliasFinder())
        _installed = True
