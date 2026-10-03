"""Бэкап и восстановление: БД (в JSON) и исходники установленных модулей одним zip-архивом.

Сессия и ``config.json`` в архив не попадают: это доступ к аккаунту.
"""

from __future__ import annotations

import io
import json
import re
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import __version__
from .database import LOADER_OWNER, Database
from .errors import LoadError

MANIFEST = "manifest.json"
DB_FILE = "db.json"
MAX_ARCHIVE = 50 * 1024 * 1024
MAX_MODULE = 2 * 1024 * 1024
_MODULE_RE = re.compile(r"^modules/([a-z0-9_]+)\.py$")


class BackupError(LoadError):
    """Архив повреждён или не похож на бэкап Uroboros."""


@dataclass
class Restored:
    keys: int
    modules: list[str]


def create(db: Database, modules_dir: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(MANIFEST, json.dumps({"uroboros": __version__, "created": int(time.time())}))
        archive.writestr(DB_FILE, json.dumps(db.dump(), ensure_ascii=False, indent=1))
        installed = db.get(LOADER_OWNER, "installed", {})
        for stem in sorted(installed):
            path = modules_dir / f"{stem}.py"
            if path.exists():
                archive.write(path, f"modules/{stem}.py")
    return buffer.getvalue()


def file_name() -> str:
    return time.strftime("uroboros-backup-%Y%m%d-%H%M%S.zip")


def _read(archive: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int) -> bytes:
    # file_size из заголовка можно подделать, поэтому читаем с ограничением.
    if info.file_size > limit:
        raise BackupError(f"Файл {info.filename} в архиве слишком большой")
    with archive.open(info) as file:
        data = file.read(limit + 1)
    if len(data) > limit:
        raise BackupError(f"Файл {info.filename} в архиве слишком большой")
    return data


def parse(data: bytes) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Проверяет архив целиком, ничего не записывая. Возвращает (БД, {stem: исходник})."""
    if len(data) > MAX_ARCHIVE:
        raise BackupError("Архив больше 50 МБ")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise BackupError("Это не zip-архив") from None

    with archive:
        names = {info.filename: info for info in archive.infolist() if not info.is_dir()}
        if MANIFEST not in names or DB_FILE not in names:
            raise BackupError("Это не бэкап Uroboros: нет manifest.json или db.json")

        modules: dict[str, str] = {}
        total = 0
        for name, info in names.items():
            if name in (MANIFEST, DB_FILE):
                continue
            match = _MODULE_RE.match(name)
            if not match:
                raise BackupError(f"Лишний файл в архиве: {name}")
            raw = _read(archive, info, MAX_MODULE)
            total += len(raw)
            try:
                modules[match[1]] = raw.decode("utf-8")
            except UnicodeDecodeError:
                raise BackupError(f"{name} не в UTF-8") from None
        if total > MAX_ARCHIVE:
            raise BackupError("Распакованный архив больше 50 МБ")

        try:
            json.loads(_read(archive, names[MANIFEST], 4096))
            dump = json.loads(_read(archive, names[DB_FILE], MAX_ARCHIVE))
        except (ValueError, UnicodeDecodeError):
            raise BackupError("Повреждён manifest.json или db.json") from None

    if not isinstance(dump, dict) or not all(
        isinstance(owner, str) and isinstance(keys, dict) for owner, keys in dump.items()
    ):
        raise BackupError("db.json: неверная структура")

    installed = dump.get(LOADER_OWNER, {}).get("installed", {})
    if not isinstance(installed, dict):
        raise BackupError("db.json: неверный список модулей")
    missing = set(installed) - set(modules)
    if missing:
        raise BackupError(f"В архиве нет файлов модулей: {', '.join(sorted(missing))}")
    return dump, modules


def restore(data: bytes, db: Database, modules_dir: Path) -> Restored:
    """Заменяет БД и модули содержимым архива. Модули подхватятся после перезапуска."""
    dump, modules = parse(data)
    return apply(dump, modules, db, modules_dir)


def apply(dump: dict[str, dict[str, Any]], modules: dict[str, str], db: Database, modules_dir: Path) -> Restored:
    """Записывает уже проверенный архив. Вызывать из потока, где открыта БД (SQLite к нему привязан).

    Сначала БД: если она не запишется, файлы модулей останутся нетронутыми.
    """
    db.replace_all(dump)
    modules_dir.mkdir(parents=True, exist_ok=True)
    for path in modules_dir.glob("*.py"):
        if path.stem not in modules:
            path.unlink()
    for stem, source in modules.items():
        (modules_dir / f"{stem}.py").write_bytes(source.encode("utf-8"))
    return Restored(keys=sum(len(keys) for keys in dump.values()), modules=sorted(modules))
