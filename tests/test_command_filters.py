import asyncio

import pytest
from conftest import FakeMessage

from uroboros import command
from uroboros.database import Database
from uroboros.decorators import COMMAND_ATTR
from uroboros.dispatcher import Dispatcher
from uroboros.loader import Command, Loader


def info_of(**filters):
    @command("x", **filters)
    async def x(message):
        pass

    return getattr(x, COMMAND_ATTR)


def msg(private=False, group=False, channel=False, chat_id=1, reply=False):
    m = FakeMessage(".x")
    m.is_private, m.is_group, m.is_channel, m.chat_id, m.is_reply = private, group, channel, chat_id, reply
    return m


@pytest.mark.parametrize(
    ("filters", "message", "allowed"),
    [
        ({}, msg(), True),
        ({"only_pm": True}, msg(private=True), True),
        ({"only_pm": True}, msg(group=True, channel=True), False),
        ({"only_groups": True}, msg(group=True, channel=True), True),
        ({"only_channels": True}, msg(group=True, channel=True), False),
        ({"only_channels": True}, msg(channel=True), True),
        ({"chats": [1, 2]}, msg(chat_id=2), True),
        ({"chats": [1, 2]}, msg(chat_id=3), False),
        ({"only_reply": True}, msg(reply=True), True),
        ({"only_reply": True}, msg(), False),
        ({"no_reply": True}, msg(reply=True), False),
        ({"filter": lambda m: m.chat_id > 5}, msg(chat_id=1), False),
    ],
)
def test_rejection(filters, message, allowed):
    assert (info_of(**filters).rejection(message) is None) is allowed


def test_conflicting_filters():
    with pytest.raises(ValueError):
        command(only_pm=True, only_groups=True)
    with pytest.raises(ValueError):
        command(only_reply=True, no_reply=True)


def test_rejected_command_is_not_called(tmp_path):
    called = []

    @command("x", only_pm=True)
    async def x(message):
        called.append(message)

    db = Database(":memory:")
    dispatcher = Dispatcher(None, db, Loader(None, db, tmp_path))
    message = msg(group=True)
    asyncio.run(dispatcher._run_command(Command(getattr(x, COMMAND_ATTR), x, None), "x", message))
    assert called == []
    assert message.edits == ["🚫 <b>Команда работает только в личных сообщениях</b>"]
