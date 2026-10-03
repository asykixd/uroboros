import asyncio
from types import SimpleNamespace

import pytest
from conftest import FakeMessage

from uroboros.client import UroborosClient
from uroboros.database import Database
from uroboros.loader import Loader
from uroboros.ratelimit import ModuleFrozen, RateLimiter, current_module, module_context


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def limiter():
    db = Database(":memory:")
    clock = Clock()
    limiter = RateLimiter(db, clock=clock)
    limiter.configure(limit=3, window=10, freeze=60)
    limiter.clock_ = clock
    yield limiter
    db.close()


EXTERNAL = SimpleNamespace(name="Spammer", is_builtin=False)
BUILTIN = SimpleNamespace(name="Help", is_builtin=True)


def test_freezes_after_limit_and_thaws(limiter):
    frozen = []
    limiter.on_freeze = lambda name, settings: frozen.append(name)
    for _ in range(3):
        limiter.check(EXTERNAL)
    with pytest.raises(ModuleFrozen, match="заморожен на 1 мин 0 с"):
        limiter.check(EXTERNAL)
    assert frozen == ["Spammer"]
    with pytest.raises(ModuleFrozen, match="ещё на"):
        limiter.check(EXTERNAL)

    limiter.clock_.now += 61
    limiter.check(EXTERNAL)
    assert limiter.frozen_for("Spammer") == 0


def test_window_slides(limiter):
    for _ in range(3):
        limiter.check(EXTERNAL)
        limiter.clock_.now += 5
    limiter.check(EXTERNAL)  # первые запросы уже вне окна


def test_builtin_and_disabled_are_not_limited(limiter):
    for _ in range(10):
        limiter.check(BUILTIN)
    limiter.configure(enabled=False)
    for _ in range(10):
        limiter.check(EXTERNAL)


def test_batched_requests_count(limiter):
    with pytest.raises(ModuleFrozen):
        limiter.check(EXTERNAL, count=4)


def test_unfreeze(limiter):
    with pytest.raises(ModuleFrozen):
        limiter.check(EXTERNAL, count=4)
    assert limiter.unfreeze("Spammer") and not limiter.unfreeze("Spammer")
    limiter.check(EXTERNAL)


def test_client_counts_only_module_requests(limiter, monkeypatch):
    sent = []

    async def fake_call(self, request, ordered=False, flood_sleep_threshold=None):
        sent.append(request)
        return request

    monkeypatch.setattr("telethon.TelegramClient.__call__", fake_call)
    client = UroborosClient.__new__(UroborosClient)
    client.limiter = limiter

    async def scenario():
        for i in range(10):
            await client(i)  # запросы ядра не считаются
        with module_context(EXTERNAL):
            for i in range(3):
                await client(i)
            with pytest.raises(ModuleFrozen):
                await client("too much")
            # задача, созданная модулем, наследует его контекст
            with pytest.raises(ModuleFrozen):
                await asyncio.get_running_loop().create_task(client("from task"))
        assert current_module.get() is None

    asyncio.run(scenario())
    assert "too much" not in sent and "from task" not in sent


SPAMMER = """
from uroboros import Module, command

class Spammer(Module):
    @command("spam")
    async def spam(self, message):
        for _ in range(5):
            await self.client("request")
"""


def test_command_of_frozen_module_reports(tmp_path):
    db = Database(":memory:")

    class Client:
        async def __call__(self, request):
            current = current_module.get()
            loader.ratelimit.check(current)

        def list_event_handlers(self):
            return []

    loader = Loader(Client(), db, tmp_path)
    loader.ratelimit.configure(limit=3, window=10, freeze=60)
    asyncio.run(loader.load_all())
    asyncio.run(loader.install(SPAMMER, "file:spammer.py"))

    from uroboros.dispatcher import Dispatcher

    dispatcher = Dispatcher(None, db, loader)
    message = FakeMessage(".spam")
    asyncio.run(dispatcher._run_command(loader.get_command("spam"), "spam", message))
    assert "заморожен на 1 мин 0 с" in message.edits[-1]

    message = FakeMessage(".security")
    asyncio.run(loader.get_command("security").func(message))
    assert "<b>Spammer</b> — ещё" in message.edits[-1]
    message = FakeMessage(".security unfreeze spammer")
    asyncio.run(loader.get_command("security").func(message))
    assert "разморожен" in message.edits[-1]
    message = FakeMessage(".security flood 10 20 30")
    asyncio.run(loader.get_command("security").func(message))
    assert loader.ratelimit.settings["limit"] == 10 and "20 с" in message.edits[-1]
    db.close()


def test_client_accepts_hikka_tl_cache_arguments(monkeypatch):
    calls = []

    async def fake_get_entity(self, entity):
        calls.append(entity)
        return entity

    monkeypatch.setattr("telethon.TelegramClient.get_entity", fake_get_entity)
    client = UroborosClient.__new__(UroborosClient)
    assert asyncio.run(client.get_entity(5, exp=0)) == 5
    assert asyncio.run(client.get_entity(6, exp=10, force=True)) == 6
    assert asyncio.run(client.force_get_entity(7)) == 7
    assert calls == [5, 6, 7]
