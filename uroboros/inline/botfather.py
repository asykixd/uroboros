"""Диалог с @BotFather от имени аккаунта: создание бота и включение inline-режима.

BotFather отвечает только по-английски, поэтому ответы сверяются с английскими фразами.
"""

from __future__ import annotations

import logging
import re
import secrets
from typing import TYPE_CHECKING

from ..errors import InlineError

if TYPE_CHECKING:
    from telethon import TelegramClient

log = logging.getLogger(__name__)

BOTFATHER = "BotFather"
TIMEOUT = 30
TOKEN_RE = re.compile(r"\d{6,}:[A-Za-z0-9_-]{30,}")
BOT_TITLE = "Uroboros"
PLACEHOLDER = "Uroboros"
USERNAME_ATTEMPTS = 3


class Conversation:
    """Вопрос — ответ с @BotFather; любой ответ, кроме ожидаемого, — понятная ошибка."""

    def __init__(self, conv):
        self._conv = conv

    async def ask(self, text: str, *expected: str) -> str:
        await self._conv.send_message(text)
        reply = (await self._conv.get_response()).raw_text or ""
        if expected and not any(phrase in reply.lower() for phrase in expected):
            raise InlineError(f"@BotFather ответил неожиданно: {reply[:300]}")
        return reply


def new_username() -> str:
    return f"uroboros_{secrets.token_hex(3)}_bot"


async def create_bot(client: TelegramClient) -> str:
    """Создаёт бота и возвращает его токен."""
    async with client.conversation(BOTFATHER, timeout=TIMEOUT, exclusive=False) as raw:
        conv = Conversation(raw)
        await conv.ask("/cancel")
        await conv.ask("/newbot", "how are we going to call it")
        await conv.ask(BOT_TITLE, "username")
        for _ in range(USERNAME_ATTEMPTS):
            username = new_username()
            reply = await conv.ask(username)
            match = TOKEN_RE.search(reply)
            if match:
                log.info("Создан inline-бот @%s", username)
                return match[0]
            if "taken" not in reply.lower():
                raise InlineError(f"@BotFather не создал бота: {reply[:300]}")
        raise InlineError("@BotFather не принял имя бота, попробуйте ещё раз: .inlinebot new")


async def setup_inline(client: TelegramClient, username: str) -> None:
    """Включает inline-режим и inline feedback (без него формы нельзя менять до первого нажатия)."""
    bot = f"@{username}"
    async with client.conversation(BOTFATHER, timeout=TIMEOUT, exclusive=False) as raw:
        conv = Conversation(raw)
        await conv.ask("/cancel")
        await conv.ask("/setinline", "choose a bot")
        await conv.ask(bot, "placeholder")
        await conv.ask(PLACEHOLDER, "success")
        await conv.ask("/setinlinefeedback", "choose a bot")
        await conv.ask(bot, "feedback")
        await conv.ask("Enabled", "success")
