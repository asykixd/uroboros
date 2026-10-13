import asyncio

import pytest
from conftest import FakeMessage
from telethon.sessions import MemorySession
from telethon.tl.functions.account import DeleteAccountRequest
from telethon.tl.functions.messages import GetDialogsRequest

from uroboros import guard
from uroboros.client import UroborosClient
from uroboros.ratelimit import module_context

MODULE = """
from uroboros import Module, command

class Demo(Module):
    @command("readfile")
    async def readfile(self, m):
        with open(m.raw_text.split(maxsplit=1)[1]) as f:
            return f.read()

    @command("session")
    async def session(self, m):
        return self.client.session
"""


@pytest.fixture
def env(builtin_loader):
    loader = builtin_loader
    asyncio.run(loader.install(MODULE, "https://example.com/demo.py"))
    data_dir = loader.modules_dir.parent
    (data_dir / "config.json").write_text("{}", encoding="utf-8")
    (data_dir / "notes.txt").write_text("ok", encoding="utf-8")
    blocked = []
    loader.guard.on_block = lambda name, action: blocked.append((name, action))
    guard.activate(loader.guard)
    yield loader, data_dir, blocked
    guard.activate(None)


def call(loader, module_name, text):
    module = loader.get_module(module_name)
    command = loader.get_command(text.split()[0])

    async def run():
        with module_context(module):
            return await command.func(FakeMessage("." + text))

    return asyncio.run(run())


def test_files_in_data_dir_are_protected(env):
    loader, data_dir, blocked = env
    assert call(loader, "demo", f"readfile {data_dir / 'notes.txt'}") == "ok"
    with pytest.raises(guard.ModuleBlocked, match=r"config\.json"):
        call(loader, "demo", f"readfile {data_dir / 'config.json'}")
    with pytest.raises(PermissionError):
        call(loader, "demo", f"readfile {data_dir / 'modules' / '..' / 'uroboros.db-journal'}")
    assert blocked and blocked[0][0] == "Demo"
    # Встроенные модули и ядро не ограничиваются.
    assert (data_dir / "config.json").read_text() == "{}"


def test_trusted_module_is_not_restricted(env):
    loader, data_dir, _ = env
    loader.guard.set_trusted("demo", True)
    assert call(loader, "demo", f"readfile {data_dir / 'config.json'}") == "{}"


def test_dangerous_requests_are_blocked(env):
    loader, _, _ = env
    module = loader.get_module("demo")
    with module_context(module), pytest.raises(guard.ModuleBlocked, match="удалить аккаунт"):
        loader.guard.check_request(DeleteAccountRequest(reason="x"))
    with module_context(module):
        loader.guard.check_request(GetDialogsRequest(None, 0, None, 10, 0))
        with pytest.raises(guard.ModuleBlocked):
            loader.guard.check_request([GetDialogsRequest(None, 0, None, 10, 0), DeleteAccountRequest(reason="x")])
    with module_context(loader.get_module("system")):
        loader.guard.check_request(DeleteAccountRequest(reason="x"))  # ядро может


def test_session_is_hidden_from_module_code(env):
    loader, _, _ = env
    client = UroborosClient(MemorySession(), 1, "hash")
    client.guard = loader.guard
    loader.get_module("demo").client = client
    with pytest.raises(guard.ModuleBlocked, match="сессию"):
        call(loader, "demo", "session")
    assert isinstance(client.session, MemorySession)  # код ядра и Telethon читает как раньше

    loader.guard.set_trusted("demo", True)
    assert call(loader, "demo", "session") is client.session


def test_confirmed_dangerous_install_is_trusted(builtin_loader):
    loader = builtin_loader
    dangerous = MODULE.replace("return self.client.session", "return self.client.session.save()")
    asyncio.run(loader.install(dangerous, "https://example.com/demo.py", force=True))
    assert loader.guard.trusted() == {"demo"}
    asyncio.run(loader.install(MODULE, "https://example.com/demo.py"))
    assert loader.guard.trusted() == set()
    asyncio.run(loader.install(dangerous, "https://example.com/demo.py", force=True))
    asyncio.run(loader.uninstall("Demo"))
    assert loader.guard.trusted() == set()


def test_security_trust_command(builtin_loader):
    loader = builtin_loader
    asyncio.run(loader.install(MODULE, "https://example.com/demo.py"))
    run = loader.get_command("security").func

    message = FakeMessage(".security trust demo")
    asyncio.run(run(message))
    assert "разрешено всё" in message.edits[-1] and loader.guard.trusted() == {"demo"}
    message = FakeMessage(".security")
    asyncio.run(run(message))
    assert "Без защиты во время работы" in message.edits[-1]
    message = FakeMessage(".security untrust demo")
    asyncio.run(run(message))
    assert "снова под защитой" in message.edits[-1] and loader.guard.trusted() == set()


def test_module_cannot_touch_system_settings(env):
    loader, _, blocked = env
    module = loader.get_module("demo")
    loader.db.set("uroboros.inline", "token", "123:abc")
    with module_context(module):
        module.db.set("own", 1)
        assert module.db.raw.get("uroboros.main", "prefix", ".") == "."
        with pytest.raises(guard.ModuleBlocked, match="системные настройки"):
            module.db.raw.set("uroboros." + "security", "owner", [42])
        with pytest.raises(guard.ModuleBlocked):
            loader.guard.set_trusted("demo", True)
        with pytest.raises(guard.ModuleBlocked):
            module.db.raw.delete("uroboros.loader", "hashes")
        with pytest.raises(guard.ModuleBlocked, match="токен"):
            module.db.raw.get("uroboros.inline", "token")
        with pytest.raises(guard.ModuleBlocked):
            module.db.raw.dump()
        with pytest.raises(guard.ModuleBlocked):
            module.db.raw.replace_all({})
    assert loader.db.get("uroboros.security", "owner") is None and loader.guard.trusted() == set()
    assert module.db.get("own") == 1 and len(blocked) == 6

    loader.guard.set_trusted("demo", True)
    with module_context(module):
        module.db.raw.set("uroboros.security", "owner", [42])


def test_module_top_level_code_is_restricted(env):
    loader, data_dir, blocked = env
    source = MODULE.replace("class Demo", f"open({str(data_dir / 'config.json')!r}).close()\n\nclass Demo")
    with pytest.raises(guard.ModuleBlocked, match=r"config\.json"):
        asyncio.run(loader.load_source(source, origin="https://example.com/demo.py", stem="demo"))
    assert blocked[-1][0] == "demo"

    opener = f"    def __init__(self):\n        open({str(data_dir / 'config.json')!r})\n"
    init = MODULE.replace("class Demo(Module):\n", "class Demo(Module):\n" + opener)
    with pytest.raises(guard.ModuleBlocked):
        asyncio.run(loader.load_source(init, origin="https://example.com/demo.py", stem="demo"))

    loader.guard.set_trusted("demo", True)
    asyncio.run(loader.load_source(source, origin="https://example.com/demo.py", stem="demo"))
