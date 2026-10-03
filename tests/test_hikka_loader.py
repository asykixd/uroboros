import asyncio

import pytest
from conftest import FakeMessage

from uroboros import download
from uroboros.database import Database
from uroboros.hikka import validators
from uroboros.loader import Loader

MODULE = """
from .. import loader, utils, version, main

class ToolsMod(loader.Module):
    strings = {"name": "Tools"}

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue("mode", "a", "Режим", validator=loader.validators.Choice(["a", "b"]),
                               on_change=self.changed),
        )
        self.changes = 0
        self.dlmod = None

    def changed(self):
        self.changes += 1

    async def on_dlmod(self, client, db):
        self.dlmod = (client, db)
        raise RuntimeError("ошибка в on_dlmod не отменяет установку, как в Hikka")

    async def toolscmd(self, message):
        mods = self.allmodules
        await utils.answer(message, f"{len(mods.modules)} {mods.get_classname('tools')} {self.get_prefix()}")

    @loader.raw_handler()
    async def raw(self, update):
        pass
"""

LIB = """
from .. import loader

class HelperLib(loader.Library):
    developer = "@me"

    async def init(self):
        self._lib_set("inited", True)

    def shout(self, text):
        return text.upper()
"""


class Client:
    def __init__(self):
        self.handlers = []

    def add_event_handler(self, callback, event):
        self.handlers.append((callback, event))

    def list_event_handlers(self):
        return list(self.handlers)

    def remove_event_handler(self, callback):
        self.handlers = [h for h in self.handlers if h[0] != callback]


@pytest.fixture
def loader(tmp_path):
    db = Database(":memory:")
    loader = Loader(Client(), db, tmp_path)
    loader.security.me_id = 1
    yield loader
    db.close()


def test_environment(loader):
    async def scenario():
        await loader.load_all()
        (inst,) = await loader.install(MODULE, "file:tools.py")
        assert inst.dlmod is not None and inst.dlmod[1] is inst.db
        assert loader.client.tg_id == 1 and loader.client.loader is not None
        assert len(loader.client.handlers) == 1

        message = FakeMessage(".tools")
        await loader.get_command("tools").func(message)
        assert message.edits[-1] == f"{len(loader.modules)} ToolsMod ."

        mods = inst.allmodules
        assert mods.lookup("toolsmod") is inst and mods.lookup("nope") is None
        assert "tools" in mods.commands and mods.tg_id == 1 and mods.client is loader.client
        assert mods.dispatch("tools")[1] is not None and mods.dispatch("nope")[1] is None
        assert isinstance(mods.aliases, dict) and isinstance(mods.watchers, list)
        assert mods.inline_handlers == {} and mods.callback_handlers == {}
        with pytest.raises(AttributeError, match="не поддерживается"):
            mods.load_module  # noqa: B018

        inst.config["mode"] = "b"
        assert inst.changes == 1
        inst.config.set_no_raise("mode", "zzz")
        assert inst.config["mode"] == "b"
        inst.config.change_validator("mode", validators.Choice(["b", "c"]))
        inst.config["mode"] = "c"
        assert inst.config.items() == [("mode", "c")] and inst.config.keys() == ["mode"]
        assert inst.config.values() == ["c"] and inst.config.get("x", 5) == 5

        assert await inst.request_join("@channel", "просьба") is False
        with pytest.raises(Exception, match="invoke"):
            await inst.invoke("help")
        assert inst.pointer("k", 3) == 3

        removed = await mods.unload_module("Tools")
        assert removed == ["Tools"] and loader.client.handlers == []

    asyncio.run(scenario())


def test_hikka_db(loader):
    async def scenario():
        (inst,) = await loader.install(MODULE, "file:tools.py")
        db = inst.db
        assert db.get("hikka.main", "command_prefix") == "."
        assert db.set("X", "k", 1) and db.get("X", "k") == 1
        assert db["X"] == {"k": 1} and "X" in db and "Y" not in db
        assert db.pointer("X", "k") == 1 and db.save()

    asyncio.run(scenario())


def test_hikka_library(loader, monkeypatch):
    async def fake_download(url):
        return LIB.encode()

    monkeypatch.setattr(download, "download", fake_download)
    user = """
from .. import loader

class UserMod(loader.Module):
    strings = {"name": "User"}

    async def client_ready(self):
        self.lib = await self.import_lib("https://example.com/helper.py", suspend_on_error=True)

    async def usecmd(self, message):
        pass
"""

    async def scenario():
        (inst,) = await loader.install(user, "file:user.py")
        assert inst.lib.shout("a") == "A" and inst.lib._lib_get("inited") is True
        assert inst.lib.tg_id == 1

    asyncio.run(scenario())


def test_version_and_main_shims(loader):
    from uroboros.hikka import main, state, version

    state.loader = loader
    assert version.__version__ >= (1, 6, 0)
    assert main.get_config_key("prefix") == "." and main.get_config_key("other") is None
