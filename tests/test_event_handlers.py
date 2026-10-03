import asyncio

from telethon import TelegramClient, events
from telethon.sessions import StringSession

from uroboros.database import Database
from uroboros.loader import Loader

SRC = """
from telethon import events
from uroboros import Module

class Hooks(Module):
    async def on_load(self):
        self.client.add_event_handler(self.method, events.NewMessage())
        self.client.add_event_handler(lambda e: None, events.MessageEdited())

        @self.client.on(events.MessageDeleted())
        async def closure(event):
            pass

    async def method(self, event):
        pass
"""


async def foreign(event):
    pass


def test_module_event_handlers_are_removed_on_unload(tmp_path):
    async def scenario():
        client = TelegramClient(StringSession(), 1, "0" * 32)
        client.add_event_handler(foreign, events.NewMessage())
        loader = Loader(client, Database(":memory:"), tmp_path)
        await loader.install(SRC, "x")
        assert len(client.list_event_handlers()) == 4
        await loader.uninstall("hooks")
        assert [cb for cb, _ in client.list_event_handlers()] == [foreign]

    asyncio.run(scenario())
