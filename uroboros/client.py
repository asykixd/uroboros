"""Создание клиента Telethon."""

from __future__ import annotations

from telethon import TelegramClient

from . import __version__
from .config import Config


def make_client(config: Config) -> TelegramClient:
    return TelegramClient(
        str(config.session_path),
        config.api_id,
        config.api_hash,
        device_model="Uroboros",
        app_version=__version__,
    )


async def login(client: TelegramClient) -> None:
    """Интерактивный логин в консоли: номер, код, пароль 2FA."""
    await client.start(
        phone=lambda: input("Номер телефона (+7...): ").strip(),
        code_callback=lambda: input("Код из Telegram: ").strip(),
    )
