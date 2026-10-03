import asyncio
from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.methods import GetMe

from uroboros.database import Database
from uroboros.errors import InlineError
from uroboros.inline import botfather
from uroboros.inline import manager as m

VALID = {"good": SimpleNamespace(id=1, username="good_bot", supports_inline_queries=True)}


BOTS = []


class FakeBot:
    def __init__(self, token, default=None):
        if ":" not in token and token not in VALID and token != "revoked":
            raise ValueError("bad token")
        self.token = token
        self.closed = False
        self.session = SimpleNamespace(close=self._close)
        BOTS.append(self)

    async def _close(self):
        self.closed = True

    async def get_me(self):
        if self.token not in VALID:
            raise TelegramUnauthorizedError(method=GetMe(), message="Unauthorized")
        return VALID[self.token]


class FakeDispatcher:
    def __init__(self):
        self.stopped = asyncio.Event()
        self.handlers = {}
        for name in ("inline_query", "chosen_inline_result", "callback_query"):
            setattr(self, name, SimpleNamespace(register=lambda f, n=name: self.handlers.__setitem__(n, f)))

    async def start_polling(self, bot, **kwargs):
        self.kwargs = kwargs
        await self.stopped.wait()

    async def stop_polling(self):
        self.stopped.set()


class Client:
    def __init__(self):
        self.handlers = []
        self.sent = []

    def add_event_handler(self, callback, event):
        self.handlers.append(callback)

    def remove_event_handler(self, callback):
        if callback in self.handlers:
            self.handlers.remove(callback)

    async def get_me(self):
        return SimpleNamespace(id=42)

    async def send_message(self, *args, **kwargs):
        self.sent.append(args)


@pytest.fixture
def manager(monkeypatch):
    monkeypatch.setattr(m, "Bot", FakeBot)
    monkeypatch.setattr(m, "Dispatcher", FakeDispatcher)
    monkeypatch.delenv(m.TOKEN_ENV, raising=False)
    configured = []

    async def fake_setup(client, username):
        configured.append(username)

    monkeypatch.setattr(botfather, "setup_inline", fake_setup)
    db = Database(":memory:")
    manager = m.InlineManager(Client(), db)
    manager.configured = configured
    yield manager
    db.close()


def test_start_runs_and_stops(manager):
    manager.db.set(m.OWNER, "token", "good")

    async def scenario():
        await manager.start()
        await asyncio.sleep(0)  # дать задаче опроса стартовать
        assert manager.ready and manager.bot_username == "good_bot" and manager.owner_id == 42
        assert manager._dp.kwargs["allowed_updates"] == m.UPDATES and not manager._dp.kwargs["handle_signals"]
        assert set(manager._dp.handlers) == {"inline_query", "chosen_inline_result", "callback_query"}
        assert manager.client.handlers
        await manager.stop()

    asyncio.run(scenario())
    assert not manager.ready and not manager.client.handlers and BOTS[-1].closed
    assert manager.configured == ["good_bot"] and manager.db.get(m.OWNER, "configured") == 1


def test_bot_without_inline_mode_is_reported(manager):
    VALID["noinline"] = SimpleNamespace(id=2, username="noinline_bot", supports_inline_queries=False)
    manager.db.set(m.OWNER, "token", "noinline")
    asyncio.run(manager.start())
    assert not manager.ready and "выключен inline-режим" in manager.error


def test_set_token_validates_first(manager):
    manager.db.set(m.OWNER, "token", "good")

    async def scenario():
        await manager.start()
        with pytest.raises(m.TokenRejected):
            await manager.set_token("revoked")
        assert manager.ready  # старый бот продолжает работать
        with pytest.raises(InlineError, match="формат"):
            await manager.set_token("garbage")
        await manager.stop()

    asyncio.run(scenario())


def test_create_bot(manager, monkeypatch):
    async def fake_create(client):
        return "good"

    monkeypatch.setattr(botfather, "create_bot", fake_create)

    async def scenario():
        await manager.start()  # токена нет — создаётся новый бот
        assert manager.ready and manager.db.get(m.OWNER, "token") == "good"
        await manager.stop()

    asyncio.run(scenario())
    assert manager.client.sent == [("good_bot", "/start")]


def test_userbot_deletes_input_marker(manager):
    deleted = []

    async def delete():
        deleted.append(True)

    manager.bot_id = 1
    message = SimpleNamespace(via_bot_id=1, raw_text=m.INPUT_MARKER, delete=delete)
    asyncio.run(manager._on_userbot_message(SimpleNamespace(message=message)))
    other = SimpleNamespace(via_bot_id=1, raw_text="обычная форма", delete=delete)
    asyncio.run(manager._on_userbot_message(SimpleNamespace(message=other)))
    assert deleted == [True]
