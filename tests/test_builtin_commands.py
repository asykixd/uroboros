import asyncio

from conftest import FakeMessage

from uroboros import download

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

    monkeypatch.setattr(download, "download", fake_download)

    text = run_command(loader, ".uplm")
    assert "без изменений" in text and "из файла, пропущен" in text

    remote["https://example.com/demo.py"] = V2.encode()
    text = run_command(loader, ".uplm demo")
    assert text.startswith("✅") and "обновлён" in text
    assert loader.get_command("one") is None
    assert loader.get_command("two") is not None


def test_dlm_asks_before_installing_from_unknown_source(builtin_loader, monkeypatch):
    loader = builtin_loader
    url = "https://raw.githubusercontent.com/someone/mods/HEAD/demo.py"

    async def fake_download(u):
        assert u == url
        return V1.encode()

    monkeypatch.setattr(download, "download", fake_download)

    text = run_command(loader, ".dlm someone/mods/demo")
    lines = f"<code>{len(V1.splitlines())}</code>"
    assert "Установить модуль?" in text and lines in text and "dlm -f someone/mods/demo" in text
    assert loader.get_command("one") is None

    assert run_command(loader, ".dlm -f someone/mods/demo").startswith("✅")
    asyncio.run(loader.uninstall("Demo"))

    loader.get_module("loader").db.set("repos", ["Someone/Mods"])
    assert run_command(loader, ".dlm someone/mods/demo").startswith("✅")
