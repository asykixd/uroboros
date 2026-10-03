import asyncio

import pytest

from uroboros import download
from uroboros.database import Database
from uroboros.loader import Loader, LoadError

LIB_URL = "https://example.com/libs/counter.py"
LIB = """
from uroboros import Library

class Counter(Library):
    loads = 0
    unloads = 0

    async def on_load(self):
        type(self).loads += 1

    async def on_unload(self):
        type(self).unloads += 1

    def hello(self):
        return "привет"
"""
PLAIN_LIB = "def double(x):\n    return x * 2\n"

USER = """
from uroboros import Module

class {name}(Module):
    async def on_load(self):
        self.lib = await self.import_lib("{url}")
"""


@pytest.fixture
def fetched(monkeypatch):
    sources = {LIB_URL: LIB.encode(), "https://example.com/plain.py": PLAIN_LIB.encode()}
    calls = []

    async def fake_download(url):
        calls.append(url)
        return sources[url]

    monkeypatch.setattr(download, "download", fake_download)
    return calls


def test_library_is_shared_and_unloaded_with_last_user(tmp_path, fetched):
    async def scenario():
        loader = Loader(None, Database(":memory:"), tmp_path / "modules")
        (a,) = await loader.install(USER.format(name="A", url=LIB_URL), "a")
        (b,) = await loader.install(USER.format(name="B", url=LIB_URL), "b")
        assert a.lib is b.lib
        assert a.lib.hello() == "привет"
        counter = type(a.lib)
        assert counter.loads == 1

        await loader.uninstall("a")
        assert LIB_URL in loader.libs and counter.unloads == 0
        await loader.uninstall("b")
        assert loader.libs == {} and counter.unloads == 1

    asyncio.run(scenario())
    assert fetched == [LIB_URL]


def test_library_source_is_cached_on_disk(tmp_path, fetched):
    db = Database(":memory:")

    async def load_once():
        loader = Loader(None, db, tmp_path / "modules")
        (inst,) = await loader.install(USER.format(name="A", url=LIB_URL), "a")
        await loader.unload_all()
        return inst

    asyncio.run(load_once())
    asyncio.run(load_once())
    assert fetched == [LIB_URL]
    assert len(list((tmp_path / "modules" / "libs").glob("*.py"))) == 1


def test_plain_python_library(tmp_path, fetched):
    loader = Loader(None, Database(":memory:"), tmp_path / "modules")
    (inst,) = asyncio.run(loader.install(USER.format(name="A", url="https://example.com/plain.py"), "a"))
    assert inst.lib.double(21) == 42


def test_broken_library_fails_module_load(tmp_path, monkeypatch):
    async def fake_download(url):
        return b"def ("

    monkeypatch.setattr(download, "download", fake_download)
    loader = Loader(None, Database(":memory:"), tmp_path / "modules")
    with pytest.raises(LoadError, match="Синтаксическая ошибка в библиотеке"):
        asyncio.run(loader.install(USER.format(name="A", url="https://example.com/bad.py"), "a"))
    assert loader.get_module("a") is None
