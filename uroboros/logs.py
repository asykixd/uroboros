"""Логирование в файл с ротацией и чтение логов для команды .logs."""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 2

_RECORD_RE = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d+ \[([A-Z]+)\]")


def setup(log_path: Path) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format=FORMAT,
        handlers=[
            logging.StreamHandler(),
            RotatingFileHandler(log_path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"),
        ],
    )
    logging.getLogger("telethon").setLevel(logging.WARNING)


def parse_level(name: str) -> int | None:
    """``"warning"``, ``"WARN"``, ``"30"`` → 30; неизвестный уровень → None."""
    name = name.strip().upper()
    if name.isdigit():
        return int(name)
    level = logging.getLevelName("WARNING" if name == "WARN" else name)
    return level if isinstance(level, int) else None


def log_files() -> list[Path]:
    """Файлы логов от старых к новым (с учётом ротации)."""
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.FileHandler):
            path = Path(handler.baseFilename)
            backups = [path.with_name(f"{path.name}.{i}") for i in range(BACKUP_COUNT, 0, -1)]
            return [p for p in (*backups, path) if p.exists()]
    return []


def filter_records(text: str, min_level: int) -> list[str]:
    """Записи уровня не ниже ``min_level``. Строки traceback относятся к предыдущей записи."""
    kept: list[str] = []
    keep = False
    for line in text.splitlines():
        match = _RECORD_RE.match(line)
        if match:
            level = logging.getLevelName(match[1])
            keep = isinstance(level, int) and level >= min_level
        if keep:
            kept.append(line)
    return kept


def read(min_level: int = logging.NOTSET) -> list[str]:
    lines: list[str] = []
    for path in log_files():
        lines += filter_records(path.read_text("utf-8", errors="replace"), min_level)
    return lines
