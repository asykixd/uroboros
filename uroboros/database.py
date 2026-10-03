"""Key-value хранилище на SQLite с кешем в памяти.

API синхронный (как ``db.get`` / ``db.set`` в Hikka): чтения идут из кеша,
запись — сразу в SQLite. Значения должны сериализоваться в JSON.
"""

from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path
from typing import Any

MAIN_OWNER = "uroboros.main"
LOADER_OWNER = "uroboros.loader"


class Database:
    def __init__(self, path: str | Path):
        self._conn = sqlite3.connect(str(path))
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS kv ("
            " owner TEXT NOT NULL,"
            " key TEXT NOT NULL,"
            " value TEXT NOT NULL,"
            " PRIMARY KEY (owner, key))"
        )
        self._conn.commit()
        self._cache: dict[tuple[str, str], Any] = {
            (owner, key): json.loads(value)
            for owner, key, value in self._conn.execute("SELECT owner, key, value FROM kv")
        }

    def get(self, owner: str, key: str, default: Any = None) -> Any:
        try:
            return copy.deepcopy(self._cache[(owner, key)])
        except KeyError:
            return default

    def set(self, owner: str, key: str, value: Any) -> None:
        data = json.dumps(value, ensure_ascii=False)
        self._conn.execute(
            "INSERT OR REPLACE INTO kv (owner, key, value) VALUES (?, ?, ?)",
            (owner, key, data),
        )
        self._conn.commit()
        # Через JSON, чтобы кеш совпадал с тем, что вернётся после рестарта (tuple → list и т.п.).
        self._cache[(owner, key)] = json.loads(data)

    def delete(self, owner: str, key: str) -> None:
        self._conn.execute("DELETE FROM kv WHERE owner = ? AND key = ?", (owner, key))
        self._conn.commit()
        self._cache.pop((owner, key), None)

    def keys(self, owner: str) -> list[str]:
        return [key for o, key in self._cache if o == owner]

    def close(self) -> None:
        self._conn.close()


class ModuleDB:
    """Обёртка над Database, привязанная к одному владельцу (модулю)."""

    def __init__(self, db: Database, owner: str):
        self.raw = db
        self.owner = owner

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(self.owner, key, default)

    def set(self, key: str, value: Any) -> None:
        self.raw.set(self.owner, key, value)

    def delete(self, key: str) -> None:
        self.raw.delete(self.owner, key)
