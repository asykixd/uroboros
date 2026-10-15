import asyncio
import datetime
from types import SimpleNamespace

from conftest import FakeMessage

from uroboros import utils
from uroboros.database import MAIN_OWNER, Database
from uroboros.decorators import CommandInfo
from uroboros.dispatcher import EDIT_COMMANDS_KEY, Dispatcher
from uroboros.loader import Command, Loader


class EditedMessage:
    """Own outgoing message; ``edit`` returns a copy with the new text, like Telethon."""

    out = True
    edit_hide = False

    def __init__(self, text, msg_id=1, age=0.0):
        self.chat_id = 100
        self.id = msg_id
        self.raw_text = text
        self.edit_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=age)
        self.edits = []

    async def edit(self, text, **kwargs):
        self.edits.append(text)
        return SimpleNamespace(chat_id=self.chat_id, id=self.id, raw_text=text.replace("<b>", "").replace("</b>", ""))


def make(tmp_path):
    db = Database(":memory:")
    loader = Loader(None, db, tmp_path)
    dispatcher = Dispatcher(None, db, loader)
    calls = []

    async def ping(message):
        calls.append(message.raw_text)
        await utils.answer(message, "<b>pong</b>")

    command = Command(CommandInfo("ping", (), ""), ping, module=None)
    dispatcher.resolve = lambda name: command if name == "ping" else None
    return dispatcher, calls, db


def edit(dispatcher, message):
    asyncio.run(dispatcher._on_edit(SimpleNamespace(message=message)))


def test_edited_command_runs(tmp_path):
    dispatcher, calls, _ = make(tmp_path)
    edit(dispatcher, EditedMessage(".ping"))
    assert calls == [".ping"]


def test_bot_reply_edit_does_not_loop(tmp_path):
    dispatcher, calls, _ = make(tmp_path)
    utils._own_edits.clear()
    message = EditedMessage(".ping", msg_id=2)
    edit(dispatcher, message)
    # Telegram reports the bot's own reply as an edit of the same message.
    edit(dispatcher, EditedMessage("pong", msg_id=2))
    assert calls == [".ping"]


def test_bot_reply_that_looks_like_a_command_is_ignored(tmp_path):
    dispatcher, calls, _ = make(tmp_path)

    async def echo(message):
        calls.append(message.raw_text)
        await utils.answer(message, ".ping")

    command = Command(CommandInfo("ping", (), ""), echo, module=None)
    dispatcher.resolve = lambda name: command
    edit(dispatcher, EditedMessage(".ping again", msg_id=3))
    edit(dispatcher, EditedMessage(".ping", msg_id=3))
    assert calls == [".ping again"]


def test_unchanged_text_is_not_rerun(tmp_path):
    dispatcher, calls, _ = make(tmp_path)
    asyncio.run(dispatcher._on_message(SimpleNamespace(message=EditedMessage(".ping", msg_id=4))))
    # Same text: a reaction or a hidden edit, not a new command.
    edit(dispatcher, EditedMessage(".ping", msg_id=4))
    assert calls == [".ping"]


def test_stale_and_hidden_edits_are_ignored(tmp_path):
    dispatcher, calls, _ = make(tmp_path)
    edit(dispatcher, EditedMessage(".ping", msg_id=5, age=3600))
    hidden = EditedMessage(".ping", msg_id=6)
    hidden.edit_hide = True
    edit(dispatcher, hidden)
    assert calls == []


def test_edit_commands_can_be_disabled(tmp_path):
    dispatcher, calls, db = make(tmp_path)
    db.set(MAIN_OWNER, EDIT_COMMANDS_KEY, False)
    edit(dispatcher, EditedMessage(".ping", msg_id=7))
    assert calls == []


def test_foreign_edit_needs_access(tmp_path):
    dispatcher, calls, _ = make(tmp_path)
    message = EditedMessage(".ping", msg_id=8)
    message.out = False
    message.sender_id = 42
    edit(dispatcher, message)
    assert calls == []


def test_editcmd_toggles_setting(builtin_loader):
    settings = builtin_loader.get_module("Settings")
    asyncio.run(settings.editcmd(FakeMessage(".editcmd off")))
    assert builtin_loader.db.get(MAIN_OWNER, EDIT_COMMANDS_KEY) is False
    message = FakeMessage(".editcmd on")
    asyncio.run(settings.editcmd(message))
    assert builtin_loader.db.get(MAIN_OWNER, EDIT_COMMANDS_KEY) is True
    assert "включены" in message.edits[-1]
