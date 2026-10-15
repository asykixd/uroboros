import asyncio
import os
import socket
import sys

import pytest
from conftest import FakeMessage

from uroboros import guard
from uroboros.ratelimit import module_context

MODULE = """{header}
import os
import socket
import subprocess

from uroboros import Module, command

class Demo(Module):
    @command("readfile")
    async def readfile(self, m):
        with open(m.raw_text.split(maxsplit=1)[1]) as f:
            return f.read()

    @command("connect")
    async def connect(self, m):
        port = int(m.raw_text.split()[1])
        with socket.socket() as s:
            try:
                s.connect(("127.0.0.1", port))
            except ConnectionError:
                pass
        return "ok"

    @command("run")
    async def run(self, m):
        return subprocess.run(["true"]).returncode

    @command("lazy")
    async def lazy(self, m):
        import wave

        return wave.__name__
"""


@pytest.fixture
def env(builtin_loader, tmp_path):
    loader = builtin_loader
    notes = tmp_path / "notes.txt"
    notes.write_text("ok", encoding="utf-8")
    blocked = []
    loader.guard.on_block = lambda name, action: blocked.append((name, action))
    guard.activate(loader.guard)
    yield loader, notes, blocked
    guard.activate(None)


def install(loader, header):
    asyncio.run(loader.install(MODULE.format(header=header), "https://example.com/demo.py"))


def call(loader, text):
    module = loader.get_module("demo")

    async def run():
        with module_context(module):
            return await loader.get_command(text.split()[0]).func(FakeMessage("." + text))

    return asyncio.run(run())


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_module_without_header_is_not_limited(env):
    loader, notes, blocked = env
    install(loader, "")
    assert loader.get_module("demo")._permissions is None
    assert call(loader, f"readfile {notes}") == "ok"
    assert call(loader, f"connect {free_port()}") == "ok"
    assert call(loader, "run") == 0
    assert blocked == []


def test_undeclared_permissions_are_blocked(env):
    loader, notes, blocked = env
    install(loader, "# meta permissions: network")
    assert call(loader, f"connect {free_port()}") == "ok"
    with pytest.raises(guard.ModuleBlocked, match="право files не объявлено"):
        call(loader, f"readfile {notes}")
    with pytest.raises(PermissionError, match="запускать команды"):
        call(loader, "run")
    assert [action for _, action in blocked] == ["работать с файлами", "запускать команды в системе"]

    # Imports and reading Python's own files are not the module's file access.
    sys.modules.pop("wave", None)
    assert call(loader, "lazy") == "wave"
    assert "def " in call(loader, f"readfile {os.__file__}")

    # The core acting for the module is not limited: here it caches a library the module imports.
    loader.libs_dir.mkdir(parents=True)
    loader.lib_path("https://example.com/lib.py").write_text("X = 1\n", encoding="utf-8")
    with module_context(loader.get_module("demo")):
        assert asyncio.run(loader.import_lib("https://example.com/lib.py", loader.get_module("demo"))).X == 1


def test_short_header_and_none(env):
    loader, notes, _ = env
    install(loader, "# permissions: files, processes")
    assert loader.get_module("demo")._permissions == {"files", "processes"}
    assert call(loader, f"readfile {notes}") == "ok"
    assert call(loader, "run") == 0
    with pytest.raises(guard.ModuleBlocked, match="выходить в сеть"):
        call(loader, f"connect {free_port()}")

    install(loader, "# meta permissions: none")
    with pytest.raises(guard.ModuleBlocked):
        call(loader, f"readfile {notes}")

    loader.guard.set_trusted("demo", True)
    assert call(loader, f"readfile {notes}") == "ok"


def test_top_level_code_is_held_to_declared_permissions(env):
    loader, notes, _ = env
    source = MODULE.format(header="# meta permissions: network") + f"\nopen({str(notes)!r}).close()\n"
    with pytest.raises(guard.ModuleBlocked, match="работать с файлами"):
        asyncio.run(loader.install(source, "https://example.com/demo.py"))
    assert loader.get_module("demo") is None
