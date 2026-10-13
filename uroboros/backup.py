"""Бэкап и восстановление: БД (в JSON) и исходники установленных модулей одним zip-архивом.

Сессия и ``config.json`` в архив не попадают: это доступ к аккаунту. В манифесте — id аккаунта, с которого
сделан бэкап: чужой бэкап восстанавливается только после подтверждения и без чужих прав доступа и бота.
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
# Из чужого бэкапа не берутся: кто управляет ботом, какие модули без защиты и чей inline-бот.
ACCOUNT_OWNERS = ("uroboros.security", "uroboros.inline")
ACCOUNT_KEYS = ((LOADER_OWNER, "trusted"),)


class BackupError(LoadError):
    """Архив повреждён или не похож на бэкап Uroboros."""


@dataclass
class Archive:
    dump: dict[str, dict[str, Any]]
    modules: dict[str, str]  # stem → исходник
    owner: int | None  # id аккаунта, с которого сделан бэкап; None — бэкап старой версии

    def is_foreign(self, me_id: int | None) -> bool:
        return self.owner is None or self.owner != me_id


@dataclass
class Restored:
    keys: int
    modules: list[str]


def create(db: Database, modules_dir: Path, owner: int | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        manifest = {"uroboros": __version__, "created": int(time.time()), "owner": owner}
        archive.writestr(MANIFEST, json.dumps(manifest))
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


def parse(data: bytes) -> Archive:
    """Проверяет архив целиком, ничего не записывая."""
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
            manifest = json.loads(_read(archive, names[MANIFEST], 4096))
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
    owner = manifest.get("owner") if isinstance(manifest, dict) else None
    return Archive(dump, modules, owner if isinstance(owner, int) and not isinstance(owner, bool) else None)


def keep_account_settings(dump: dict[str, dict[str, Any]], db: Database) -> dict[str, dict[str, Any]]:
    """Копия ``dump``, в которой права доступа, доверенные модули и inline-бот — из текущей БД."""
    result = {owner: dict(keys) for owner, keys in dump.items() if owner not in ACCOUNT_OWNERS}
    for owner in ACCOUNT_OWNERS:
        current = {key: db.get(owner, key) for key in db.keys(owner)}
        if current:
            result[owner] = current
    for owner, key in ACCOUNT_KEYS:
        result.get(owner, {}).pop(key, None)
        value = db.get(owner, key)
        if value is not None:
            result.setdefault(owner, {})[key] = value
    return result


def restore(data: bytes, db: Database, modules_dir: Path) -> Restored:
    """Заменяет БД и модули содержимым архива. Модули подхватятся после перезапуска."""
    archive = parse(data)
    return apply(archive.dump, archive.modules, db, modules_dir)


def apply(dump: dict[str, dict[str, Any]], modules: dict[str, str], db: Database, modules_dir: Path) -> Restored:
    """Записывает уже проверенный архив. Вызывать из потока, где открыта БД (SQLite к нему привязан).

    Сначала БД: если она не запишется, файлы модулей останутся нетронутыми. После записи БД заморожена
    до перезапуска, чтобы ещё работающие модули не затёрли восстановленные значения.
    """
    db.replace_all(dump)
    db.freeze()
    modules_dir.mkdir(parents=True, exist_ok=True)
    for path in modules_dir.glob("*.py"):
        if path.stem not in modules:
            path.unlink()
    for stem, source in modules.items():
        (modules_dir / f"{stem}.py").write_bytes(source.encode("utf-8"))
    return Restored(keys=sum(len(keys) for keys in dump.values()), modules=sorted(modules))
