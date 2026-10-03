"""Утилиты для модулей."""

from __future__ import annotations

import html
import io
import os
import re
import shlex
import sys
import time
from typing import TYPE_CHECKING

from .config import DEFAULT_PREFIX
from .database import MAIN_OWNER

if TYPE_CHECKING:
    from telethon import TelegramClient
    from telethon.tl.custom import Message

    from .database import Database

START_TIME = time.time()
MAX_MESSAGE_LENGTH = 4096

_restart_requested = False

IS_WINDOWS = os.name == "nt"
RESTART_EXIT_CODE = 75
SUPERVISED_ENV = "UROBOROS_SUPERVISED"


class Html(str):
    """Строка, которая уже является HTML: ``escape_html`` и ``strings`` её не экранируют."""


def escape_html(text: object) -> str:
    if isinstance(text, Html):
        return text
    return html.escape(str(text), quote=False)


def quote(text: str, *, expandable: bool = False) -> str:
    """Цитата Telegram; ``expandable`` — свёрнутая, раскрывается по нажатию."""
    return f"<blockquote{' expandable' if expandable else ''}>{text}</blockquote>"


def get_args_raw(message: Message) -> str:
    """Всё, что после команды, как есть."""
    parts = (message.raw_text or "").split(maxsplit=1)
    return parts[1] if len(parts) > 1 else ""


def get_args(message: Message) -> list[str]:
    """Аргументы команды с учётом кавычек."""
    raw = get_args_raw(message)
    try:
        return shlex.split(raw)
    except ValueError:
        return raw.split()


def get_prefix(db: Database) -> str:
    return db.get(MAIN_OWNER, "prefix", DEFAULT_PREFIX)


def _strip_html(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text))


async def answer(message: Message, text: str, **kwargs) -> Message:
    """Отвечает на команду: редактирует своё сообщение или отвечает на чужое.

    Слишком длинный текст отправляется файлом. Короткий флуд-лимит Telethon выжидает сам
    (``flood_sleep_threshold``), длинный приходит как ``FloodWaitError`` — диспетчер сообщит о нём.
    """
    kwargs.setdefault("parse_mode", "html")
    kwargs.setdefault("link_preview", False)

    if len(text) > MAX_MESSAGE_LENGTH:
        file = io.BytesIO(_strip_html(text).encode())
        file.name = "output.txt"
        await message.respond(
            "📄 Вывод слишком длинный, он во вложении",
            file=file,
            reply_to=message.id,
        )
        text = "📄 Вывод отправлен файлом"
        kwargs.pop("file", None)

    if message.out:
        from telethon.errors import MessageNotModifiedError

        try:
            return await message.edit(text, **kwargs)
        except MessageNotModifiedError:
            return message
    return await message.reply(text, **kwargs)


def format_duration(seconds: float) -> str:
    seconds = int(seconds)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    parts = [f"{days} д"] if days else []
    parts.append(f"{hours:02}:{minutes:02}:{seconds:02}")
    return " ".join(parts)


async def restart(client: TelegramClient) -> None:
    """Перезапускает юзербота: отключает клиент, процесс перезапустится в main()."""
    global _restart_requested
    _restart_requested = True
    await client.disconnect()


def restart_requested() -> bool:
    return _restart_requested


def exec_restart() -> None:
    """Перезапускает процесс. На POSIX — ``os.execv`` (PID сохраняется, удобно для systemd).

    На Windows ``execv`` ломает консоль, поэтому там бот работает под процессом-надзирателем
    (см. ``main.supervise``): достаточно выйти с кодом ``RESTART_EXIT_CODE``.
    """
    if IS_WINDOWS:
        sys.exit(RESTART_EXIT_CODE)
    os.execv(sys.executable, restart_args())


def restart_args() -> list[str]:
    return [sys.executable, "-m", "uroboros", *sys.argv[1:]]
