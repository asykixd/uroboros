"""Создание клиента Telethon."""

from __future__ import annotations

from telethon import TelegramClient

from . import __version__
from .config import Config
from .ratelimit import RateLimiter, current_module


class UroborosClient(TelegramClient):
    """TelegramClient, который считает запросы сторонних модулей (защита от флуда)."""

    limiter: RateLimiter | None = None

    async def __call__(self, request, ordered=False, flood_sleep_threshold=None):
        module = current_module.get()
        if module is not None and self.limiter is not None:
            self.limiter.check(module, len(request) if isinstance(request, list) else 1)
        return await super().__call__(request, ordered, flood_sleep_threshold)

    # --- совместимость с Hikka-TL: модули Hikka передают параметры кеша (exp, force) ---

    async def get_entity(self, entity, exp=None, force=False):
        return await super().get_entity(entity)

    async def force_get_entity(self, entity):
        return await super().get_entity(entity)

    async def get_perms_cached(self, entity, user=None, exp=None, force=False):
        return await self.get_permissions(entity, user)

    async def get_fullchannel(self, entity, exp=None, force=False):
        from telethon.tl.functions.channels import GetFullChannelRequest

        return await self(GetFullChannelRequest(entity))

    async def get_fulluser(self, entity, exp=None, force=False):
        from telethon.tl.functions.users import GetFullUserRequest

        return await self(GetFullUserRequest(entity))


def make_client(config: Config) -> UroborosClient:
    return UroborosClient(
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
