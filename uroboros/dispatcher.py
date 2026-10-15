"""Маршрутизация входящих сообщений в команды и вотчеры."""

from __future__ import annotations

import asyncio
import logging
import time
import traceback
from typing import TYPE_CHECKING

from telethon import events
from telethon.errors import FloodWaitError

from . import utils
from .database import MAIN_OWNER, Database
from .loader import Command, Loader, LoadError
from .ratelimit import ModuleFrozen, module_context

if TYPE_CHECKING:
    from telethon import TelegramClient
    from telethon.tl.custom import Message

log = logging.getLogger(__name__)

EDIT_COMMANDS_KEY = "edit_commands"
# Older edits are not re-run: reactions and catch-up after a reconnect also arrive as edits.
EDIT_MAX_AGE = 300
_HANDLED_LIMIT = 512


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
        self._running: set[tuple] = set()
        # Command text already run per message: an edit that doesn't change it (a reaction) is skipped.
        self._handled: dict[tuple, str] = {}

    @property
    def prefix(self) -> str:
        return utils.get_prefix(self.db)

    @property
    def aliases(self) -> dict[str, str]:
        return self.db.get(MAIN_OWNER, "aliases", {})

    @property
    def edit_commands(self) -> bool:
        return bool(self.db.get(MAIN_OWNER, EDIT_COMMANDS_KEY, True))

    def install(self) -> None:
        self.client.add_event_handler(self._on_message, events.NewMessage())
        self.client.add_event_handler(self._on_edit, events.MessageEdited())

    def resolve(self, name: str) -> Command | None:
        return self.loader.get_command(self.aliases.get(name, name))

    async def _on_message(self, event: events.NewMessage.Event) -> None:
        message = event.message
        await self._handle_command(message)

        watchers = [w for w in self.loader.watchers if self._safe_match(w, message)]
        if watchers:
            await asyncio.gather(*(self._run_watcher(w, message) for w in watchers))

    async def _on_edit(self, event: events.MessageEdited.Event) -> None:
        """Re-runs a command whose message was edited (``.pnig`` → ``.ping``). Watchers don't see edits."""
        message = event.message
        if not self.edit_commands or not self._is_fresh_edit(message):
            return
        key = utils._message_key(message)
        # While the command runs it edits its own message with the reply; afterwards utils.answer remembers
        # what it wrote. Either way it's the bot's edit, not the user's.
        if key in self._running or utils._is_own_edit(message) or self._handled.get(key) == message.raw_text:
            return
        await self._handle_command(message)

    @staticmethod
    def _is_fresh_edit(message: Message) -> bool:
        if getattr(message, "edit_hide", False):
            return False
        edit_date = getattr(message, "edit_date", None)
        return edit_date is not None and time.time() - edit_date.timestamp() <= EDIT_MAX_AGE

    async def _handle_command(self, message: Message) -> None:
        if not message.raw_text:
            return
        parsed = parse_command(message.raw_text, self.prefix)
        if not parsed:
            return
        command = self.resolve(parsed[0])
        if command is None or not self.may_run(command, message):
            return
        key = utils._message_key(message)
        self._remember_handled(key, message.raw_text)
        self._running.add(key)
        try:
            await self._run_command(command, parsed[0], message)
        finally:
            self._running.discard(key)

    def _remember_handled(self, key: tuple, text: str) -> None:
        self._handled.pop(key, None)
        self._handled[key] = text
        while len(self._handled) > _HANDLED_LIMIT:
            del self._handled[next(iter(self._handled))]

    def may_run(self, command: Command, message: Message) -> bool:
        """Свои сообщения — всегда; чужие — если отправителю хватает прав (``.security``)."""
        if message.out:
            return True
        return self.loader.security.can_run(command, message.sender_id)

    @staticmethod
    def _safe_match(watcher, message) -> bool:
        try:
            return watcher.matches(message)
        except Exception:
            log.exception("Ошибка в фильтре вотчера %s", watcher.module.name)
            return False

    async def _run_command(self, command: Command, used_name: str, message: Message) -> None:
        try:
            reason = command.info.rejection(message)
            if reason is not None:
                await utils.answer(message, f"🚫 <b>{utils.escape_html(reason)}</b>")
                return
            await self._timed(command, message)
        except LoadError as e:
            await self._report(message, used_name, utils.quote(utils.escape_html(e)))
        except FloodWaitError as e:
            # Короткие ожидания (до flood_sleep_threshold) Telethon выжидает сам, сюда доходят длинные.
            log.warning("Команда %s: флуд-лимит Telegram, ждать %d с", used_name, e.seconds)
            await self._report(
                message,
                used_name,
                utils.quote(
                    f"⏳ Telegram ограничил частоту запросов, повторите через {utils.format_duration(e.seconds)}"
                ),
            )
        except (Exception, SystemExit):  # sys.exit() в модуле не должен останавливать бота
            log.exception("Ошибка в команде %s", used_name)
            tb = traceback.format_exc(limit=-5)
            await self._report(
                message, used_name, utils.quote(f"<code>{utils.escape_html(tb[-3000:])}</code>", expandable=True)
            )

    async def _timed(self, command: Command, message: Message) -> None:
        stats = self.loader.stats
        started = stats.clock()
        failed = True
        try:
            with module_context(command.module):
                await command.func(message)
            failed = False
        finally:
            stats.record_command(command.module.name, command.name, stats.clock() - started, failed=failed)

    async def _report(self, message: Message, used_name: str, body: str) -> None:
        text = f"❌ <b>Ошибка в команде</b> <code>{utils.escape_html(self.prefix + used_name)}</code>\n{body}"
        try:
            await utils.answer(message, text)
        except FloodWaitError as e:
            log.warning("Не удалось сообщить об ошибке: флуд-лимит Telegram, ждать %d с", e.seconds)
        except Exception:
            log.exception("Не удалось отправить сообщение об ошибке")

    async def _run_watcher(self, watcher, message: Message) -> None:
        try:
            with module_context(watcher.module):
                await watcher.func(message)
        except ModuleFrozen:
            pass  # о заморозке уже сообщили, вотчер просто пропускает сообщения
        except FloodWaitError as e:
            log.warning("Вотчер модуля %s: флуд-лимит Telegram, ждать %d с", watcher.module.name, e.seconds)
        except (Exception, SystemExit):
            log.exception("Ошибка в вотчере модуля %s", watcher.module.name)
            self.loader.stats.watcher_errors[watcher.module.name] += 1
