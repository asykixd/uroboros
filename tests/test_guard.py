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
    (data_dir / "config.json").write_text("{}")
    (data_dir / "notes.txt").write_text("ok")
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
    assert open(data_dir / "config.json").read() == "{}"  # noqa: SIM115


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
