import asyncio

from telethon.errors import FloodWaitError

from uroboros.database import Database
from uroboros.decorators import CommandInfo
from uroboros.dispatcher import Dispatcher
from uroboros.loader import Command, Loader


class FakeMessage:
    out = True
    raw_text = ".flood"

    def __init__(self, fail_edit=False):
        self.edits = []
        self.fail_edit = fail_edit

    async def edit(self, text, **kwargs):
        if self.fail_edit:
            raise FloodWaitError(request=None, capture=300)
        self.edits.append(text)
        return self


def make_dispatcher(tmp_path):
    db = Database(":memory:")
    loader = Loader(None, db, tmp_path)
    return Dispatcher(None, db, loader)


async def flood(message):
    raise FloodWaitError(request=None, capture=300)


def test_flood_wait_is_reported_without_traceback(tmp_path):
    dispatcher = make_dispatcher(tmp_path)
    command = Command(CommandInfo("flood", (), ""), flood, module=None)
    message = FakeMessage()
    asyncio.run(dispatcher._run_command(command, "flood", message))
    (text,) = message.edits
    assert "частоту запросов" in text and "00:05:00" in text
    assert "Traceback" not in text


def test_flood_wait_while_reporting_is_swallowed(tmp_path):
    dispatcher = make_dispatcher(tmp_path)
    command = Command(CommandInfo("flood", (), ""), flood, module=None)
    asyncio.run(dispatcher._run_command(command, "flood", FakeMessage(fail_edit=True)))


async def leave(message):
    raise SystemExit(0)


def test_sys_exit_in_command_is_reported(tmp_path):
    dispatcher = make_dispatcher(tmp_path)
    command = Command(CommandInfo("leave", (), ""), leave, module=None)
    message = FakeMessage()
    asyncio.run(dispatcher._run_command(command, "leave", message))
    assert "SystemExit" in message.edits[-1]


def test_sys_exit_in_watcher_is_logged(tmp_path, caplog):
    watcher = type("W", (), {"func": staticmethod(leave), "module": type("M", (), {"name": "Demo"})()})()
    asyncio.run(Dispatcher._run_watcher(watcher, FakeMessage()))
    assert "Demo" in caplog.text
