"""Маршрутизация входящих сообщений в команды и вотчеры."""

from __future__ import annotations

import asyncio
import logging
import traceback
from typing import TYPE_CHECKING

from telethon import events
from telethon.errors import FloodWaitError

from . import utils
from .database import MAIN_OWNER, Database
from .loader import Command, Loader, LoadError

if TYPE_CHECKING:
    from telethon import TelegramClient
    from telethon.tl.custom import Message

log = logging.getLogger(__name__)


def parse_command(text: str, prefix: str) -> tuple[str, str] | None:
    """``".ping 1 2"`` → ``("ping", "1 2")``; не команда → None."""
    if not prefix or not text.startswith(prefix):
        return None
    body = text[len(prefix) :]
    if not body or body[0].isspace():
        return None
    parts = body.split(maxsplit=1)
    return parts[0].lower(), parts[1] if len(parts) > 1 else ""


class Dispatcher:
    def __init__(self, client: TelegramClient, db: Database, loader: Loader):
        self.client = client
        self.db = db
        self.loader = loader
        loader.dispatcher = self

    @property
    def prefix(self) -> str:
        return utils.get_prefix(self.db)

    @property
    def aliases(self) -> dict[str, str]:
        return self.db.get(MAIN_OWNER, "aliases", {})

    def install(self) -> None:
        self.client.add_event_handler(self._on_message, events.NewMessage())

    def resolve(self, name: str) -> Command | None:
        return self.loader.get_command(self.aliases.get(name, name))

    async def _on_message(self, event: events.NewMessage.Event) -> None:
        message = event.message

        if message.out and message.raw_text:
            parsed = parse_command(message.raw_text, self.prefix)
            if parsed:
                command = self.resolve(parsed[0])
                if command is not None:
                    await self._run_command(command, parsed[0], message)

        watchers = [w for w in self.loader.watchers if self._safe_match(w, message)]
        if watchers:
            await asyncio.gather(*(self._run_watcher(w, message) for w in watchers))

    @staticmethod
    def _safe_match(watcher, message) -> bool:
        try:
            return watcher.matches(message)
        except Exception:
            log.exception("Ошибка в фильтре вотчера %s", watcher.module.name)
            return False

    async def _run_command(self, command: Command, used_name: str, message: Message) -> None:
        try:
            await command.func(message)
        except LoadError as e:
            await self._report(message, used_name, utils.quote(utils.escape_html(e)))
        except FloodWaitError as e:
            # Короткие ожидания (до flood_sleep_threshold) Telethon выжидает сам, сюда доходят длинные.
            log.warning("Команда %s: флуд-лимит Telegram, ждать %d с", used_name, e.seconds)
            await self._report(
                message,
                used_name,
                utils.quote(f"Telegram ограничил частоту запросов, повторите через {utils.format_duration(e.seconds)}"),
            )
        except Exception:
            log.exception("Ошибка в команде %s", used_name)
            tb = traceback.format_exc(limit=-5)
            await self._report(
                message, used_name, utils.quote(f"<code>{utils.escape_html(tb[-3000:])}</code>", expandable=True)
            )

    async def _report(self, message: Message, used_name: str, body: str) -> None:
        text = f"❌ <b>Ошибка в команде</b> <code>{utils.escape_html(self.prefix + used_name)}</code>\n{body}"
        try:
            await utils.answer(message, text)
        except FloodWaitError as e:
            log.warning("Не удалось сообщить об ошибке: флуд-лимит Telegram, ждать %d с", e.seconds)
        except Exception:
            log.exception("Не удалось отправить сообщение об ошибке")

    @staticmethod
    async def _run_watcher(watcher, message: Message) -> None:
        try:
            await watcher.func(message)
        except FloodWaitError as e:
            log.warning("Вотчер модуля %s: флуд-лимит Telegram, ждать %d с", watcher.module.name, e.seconds)
        except Exception:
            log.exception("Ошибка в вотчере модуля %s", watcher.module.name)
