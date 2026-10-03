import asyncio

from conftest import FakeMessage, builtin_globals

V1 = """
from uroboros import Module, command

class Demo(Module):
    @command("one")
    async def one(self, m):
        pass
"""
V2 = V1.replace('"one"', '"two"')


def run_command(loader, text):
    message = FakeMessage(text)
    name = text.split()[0][1:]
    asyncio.run(loader.get_command(name).func(message))
    return message.edits[-1]


def test_uplm_updates_changed_modules(builtin_loader, monkeypatch):
    loader = builtin_loader
    asyncio.run(loader.install(V1, "https://example.com/demo.py"))
    asyncio.run(loader.install(V1.replace("Demo", "Local").replace('"one"', '"loc"'), "file:local.py"))

    remote = {"https://example.com/demo.py": V1.encode()}

    async def fake_download(url):
        return remote[url]

    monkeypatch.setitem(builtin_globals("loader_cmds"), "_download", fake_download)

    text = run_command(loader, ".uplm")
    assert "без изменений" in text and "из файла, пропущен" in text

    remote["https://example.com/demo.py"] = V2.encode()
    text = run_command(loader, ".uplm demo")
    assert text.startswith("✅") and "обновлён" in text
    assert loader.get_command("one") is None
    assert loader.get_command("two") is not None
