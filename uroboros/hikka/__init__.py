"""Адаптер модулей Hikka и FTG.

Модуль Hikka исполняется как подмодуль пакета ``uroboros.hikka.modules``, поэтому его
``from .. import loader, utils`` получает шимы из этого пакета: ``loader`` (базовый класс,
декораторы, конфиг), ``utils``, ``validators``, ``inline.types``. Импорт ``hikkatl``
(форк Telethon в Hikka) отдаёт обычный Telethon. Всё остальное, что есть только внутри
Hikka, отклоняется при загрузке с понятной ошибкой.
"""

from __future__ import annotations

import re
from typing import Any

from ..errors import LoadError

PACKAGE = "uroboros.hikka.modules"

# Версия Hikka, API которой повторяет адаптер: для ``# scope: hikka_min`` и ``version.__version__``.
HIKKA_VERSION = (1, 6, 3)

# Признаки модулей Hikka/FTG: относительный импорт ядра, их форк Telethon, @loader.tds, loader.Module.
HIKKA_RE = re.compile(
    r"^\s*from\s+\.\.(?:\s+import\b|\w)"
    r"|^\s*(?:from|import)\s+(?:hikkatl|hikka|telethon_hikka)\b"
    r"|^\s*@loader\.tds\b"
    r"|^\s*class\s+\w+\s*\(\s*loader\.Module\s*\)",
    re.MULTILINE,
)

# Что из ядра Hikka можно импортировать: ``from .. import X`` и ``from ..X import ...``.
SUPPORTED = {"loader", "utils", "validators", "security", "version", "main", "types", "inline", "inline.types"}

UNSUPPORTED_IMPORTS = {
    "hikka": "ядро Hikka целиком (import hikka)",
    "hikkapyro": "Pyrogram-клиент Hikka",
    "pyrogram": "Pyrogram (Uroboros работает только на Telethon)",
    "telethon_hikka": "старое название форка Telethon из Hikka",
    "herokutl": "форк Telethon из Heroku",
}

RELATIVE_RE = re.compile(r"^\s*from\s+\.\.([\w.]*)\s+import\s+([^\n#]+)", re.MULTILINE)
ABSOLUTE_RE = re.compile(r"^\s*(?:from|import)\s+(\w+)", re.MULTILINE)
SCOPE_MIN_RE = re.compile(r"^\s*#\s*scope:\s*hikka_min\s+([\d.]+)", re.MULTILINE)
SCOPE_RE = re.compile(r"^\s*#\s*scope:\s*(\w+)", re.MULTILINE)


def is_hikka(source: str) -> bool:
    return bool(HIKKA_RE.search(source))


def _names(clause: str) -> list[str]:
    clause = clause.strip().strip("()").replace("\\", " ")
    return [part.split(" as ")[0].strip() for part in clause.split(",") if part.strip()]


def check_supported(source: str) -> None:
    """Отклоняет модули, которым нужны части Hikka, которых в Uroboros нет."""
    for module, clause in RELATIVE_RE.findall(source):
        if module:
            if module not in SUPPORTED:
                raise LoadError(f"Модуль использует внутренности Hikka (..{module}), в Uroboros их нет")
            continue
        for name in _names(clause):
            if name not in SUPPORTED:
                raise LoadError(f"Модуль использует внутренности Hikka (from .. import {name}), в Uroboros их нет")

    for name in ABSOLUTE_RE.findall(source):
        if name in UNSUPPORTED_IMPORTS:
            raise LoadError(f"Модулю нужен {UNSUPPORTED_IMPORTS[name]} — в Uroboros этого нет")

    if "hikka_only" in SCOPE_RE.findall(source):
        raise LoadError("Модуль помечен как только для Hikka (# scope: hikka_only)")
    match = SCOPE_MIN_RE.search(source)
    if match:
        required = tuple(int(part) for part in match[1].split(".") if part.isdigit())
        if required > HIKKA_VERSION:
            shown = ".".join(map(str, HIKKA_VERSION))
            raise LoadError(f"Модулю нужен Hikka {match[1]} или новее, адаптер Uroboros повторяет API Hikka {shown}")


def module_meta(pymod: Any) -> dict[str, str]:
    """``__version__ = (1, 2, 0)`` в модуле Hikka → версия для ``.help``."""
    version = getattr(pymod, "__version__", None)
    if isinstance(version, (tuple, list)) and all(isinstance(v, int) for v in version):
        return {"version": ".".join(map(str, version))}
    if isinstance(version, str):
        return {"version": version}
    return {}
