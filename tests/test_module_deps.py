import asyncio

import pytest
from conftest import FakeMessage

from uroboros import download
from uroboros.loader import LoadError, MissingModulesError, parse_requires_modules, same_module_url

RAW = "https://raw.githubusercontent.com/someone/mods/HEAD"


def module(name, *requires):
    header = "".join(f"# requires_module: {spec}\n" for spec in requires)
    return (
        f"{header}from uroboros import Module, command\n\n"
        f"class {name.title()}(Module):\n"
        f"    @command('{name}')\n"
        f"    async def cmd(self, m):\n"
        f"        pass\n"
    )


def serve(monkeypatch, files):
    downloads = []

    async def fake_download(url):
        downloads.append(url)
        return files[url].encode()

    monkeypatch.setattr(download, "download", fake_download)
    return downloads


def run_command(loader, text):
    message = FakeMessage(text)
    asyncio.run(loader.get_command(text.split()[0][1:]).func(message))
    return message.edits[-1]


def test_parse_requires_modules():
    source = (
        "# requires_module: someone/mods/base\n"
        "# requires_module: https://github.com/someone/mods/blob/main/extra.py someone/mods/base.py\n"
    )
    assert parse_requires_modules(source) == [
        f"{RAW}/base.py",
        "https://raw.githubusercontent.com/someone/mods/main/extra.py",
    ]
    with pytest.raises(LoadError, match="requires_module"):
        parse_requires_modules("# requires_module: base\n")


def test_same_module_url_ignores_ref():
    assert same_module_url(f"{RAW}/base.py", "https://raw.githubusercontent.com/Someone/mods/" + "1" * 40 + "/base.py")
    assert not same_module_url(f"{RAW}/base.py", f"{RAW}/other.py")
    assert not same_module_url("https://example.com/a.py", "https://example.com/b.py")


def test_core_refuses_module_with_missing_dependency(builtin_loader):
    loader = builtin_loader
    with pytest.raises(MissingModulesError) as error:
        asyncio.run(loader.install(module("top", "someone/mods/base"), "file:top.py"))
    assert error.value.urls == [f"{RAW}/base.py"] and loader.get_module("top") is None

    asyncio.run(loader.install(module("base"), f"{RAW}/base.py"))
    asyncio.run(loader.install(module("top", "someone/mods/base"), "file:top.py"))
    assert loader.get_module("top") is not None


def test_dlm_installs_dependency_chain(builtin_loader, monkeypatch):
    loader = builtin_loader
    loader.get_module("loader").db.set("repos", ["someone/mods"])
    downloads = serve(
        monkeypatch,
        {
            f"{RAW}/top.py": module("top", "someone/mods/mid", "someone/mods/base"),
            f"{RAW}/mid.py": module("mid", "someone/mods/base"),
            f"{RAW}/base.py": module("base"),
        },
    )
    text = run_command(loader, ".dlm someone/mods/top")
    assert text.count("✅") == 3 and "Модуль Top загружен" in text
    assert list(loader.installed()) == ["base", "mid", "top"]  # dependencies first, base downloaded once
    assert downloads == [f"{RAW}/top.py", f"{RAW}/mid.py", f"{RAW}/base.py"]

    # Already installed dependencies aren't downloaded again.
    asyncio.run(loader.uninstall("Top"))
    downloads.clear()
    assert run_command(loader, ".dlm someone/mods/top").startswith("✅")
    assert downloads == [f"{RAW}/top.py"]


def test_dlm_rejects_dependency_cycle(builtin_loader, monkeypatch):
    loader = builtin_loader
    loader.get_module("loader").db.set("repos", ["someone/mods"])
    serve(
        monkeypatch,
        {
            f"{RAW}/a.py": module("a", "someone/mods/b"),
            f"{RAW}/b.py": module("b", "someone/mods/a"),
        },
    )
    with pytest.raises(LoadError, match=r"Циклическая зависимость модулей: .*/a\.py → .*/b\.py → .*/a\.py"):
        run_command(loader, ".dlm someone/mods/a")
    assert loader.installed() == {}


def test_untrusted_dependency_needs_confirmation(builtin_loader, monkeypatch):
    loader = builtin_loader
    loader.get_module("loader").db.set("repos", ["someone/mods"])
    stranger = "https://example.com/helper.py"
    serve(
        monkeypatch,
        {
            f"{RAW}/top.py": module("top", stranger),
            stranger: module("helper").replace(
                "pass", "await self.client.send_message('me', self.client.session.save())"
            ),
        },
    )
    text = run_command(loader, ".dlm someone/mods/top")
    assert text.startswith("🚨") and "Зависимостей: <code>1</code>" in text
    assert f"🧩 <b>Зависимость</b> <code>{stranger}</code>" in text and "dlm -f someone/mods/top" in text
    assert loader.installed() == {}

    assert run_command(loader, ".dlm -f someone/mods/top").startswith("✅")
    assert list(loader.installed()) == ["helper", "top"]
