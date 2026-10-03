"""Пути и учётные данные приложения Telegram (api_id / api_hash)."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PREFIX = "."


@dataclass(frozen=True)
class Config:
    api_id: int
    api_hash: str
    data_dir: Path

    @property
    def session_path(self) -> Path:
        return self.data_dir / "uroboros"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "uroboros.db"

    @property
    def modules_dir(self) -> Path:
        return self.data_dir / "modules"

    @property
    def lock_path(self) -> Path:
        return self.data_dir / "uroboros.lock"

    @property
    def log_path(self) -> Path:
        return self.data_dir / "uroboros.log"


def get_data_dir() -> Path:
    path = Path(os.environ.get("UROBOROS_DATA") or Path.cwd() / "data").resolve()
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        # Здесь лежит сессия: доступ к ней = доступ к аккаунту.
        path.chmod(0o700)
    return path


def _valid(api_id: str | None, api_hash: str | None) -> bool:
    return bool(api_id and str(api_id).isdigit() and api_hash and re.fullmatch(r"[0-9a-f]{32}", api_hash))


def save_credentials(data_dir: Path, api_id: int, api_hash: str) -> None:
    path = data_dir / "config.json"
    path.write_text(json.dumps({"api_id": int(api_id), "api_hash": api_hash}), "utf-8")
    if os.name == "posix":
        path.chmod(0o600)


def valid_credentials(api_id: object, api_hash: object) -> bool:
    return _valid(None if api_id is None else str(api_id), None if api_hash is None else str(api_hash))


def load_config(*, prompt: bool = True) -> Config | None:
    """Конфиг из окружения и ``config.json``. Нет api_id/api_hash: ``prompt`` — спросить в консоли, иначе None."""
    data_dir = get_data_dir()
    path = data_dir / "config.json"
    stored = json.loads(path.read_text("utf-8")) if path.exists() else {}

    api_id = os.environ.get("UROBOROS_API_ID") or stored.get("api_id")
    api_hash = os.environ.get("UROBOROS_API_HASH") or stored.get("api_hash")

    if not valid_credentials(api_id, api_hash):
        if not prompt:
            return None
        print("Получите api_id и api_hash на https://my.telegram.org/apps")
        while True:
            api_id = input("api_id: ").strip()
            api_hash = input("api_hash: ").strip().lower()
            if _valid(api_id, api_hash):
                break
            print("api_id должен быть числом, api_hash — 32 hex-символа. Попробуйте ещё раз.")
        save_credentials(data_dir, int(api_id), api_hash)

    return Config(api_id=int(api_id), api_hash=api_hash, data_dir=data_dir)
