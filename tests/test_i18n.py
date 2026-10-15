import asyncio
from pathlib import Path

from conftest import FakeMessage

from uroboros import utils
from uroboros.database import MAIN_OWNER

TRANSLATED = """
from uroboros import Module, command

class Greeter(Module):
    \"\"\"Greets\"\"\"

    strings = {"hi": "Hello, {name}!", "only_base": "base"}
    strings_ru = {"hi": "Привет, {name}!", "_cls_doc": "Здоровается", "_cmd_doc_hi": "— поздороваться"}

    @command("hi")
    async def hi(self, m):
        \"\"\"— say hello\"\"\"
"""
HIKKA_DEMO = (Path(__file__).parent / "hikka" / "demo.py").read_text("utf-8")


def run(loader, text):
    message = FakeMessage(text)
    asyncio.run(loader.get_command(text.split()[0][1:]).func(message))
    return message.edits[-1]


def test_language_defaults_to_russian(builtin_loader):
    db = builtin_loader.db
    assert utils.get_language(db) == "ru"
    db.set(MAIN_OWNER, "lang", "xx")  # garbage in the DB falls back to the default
    assert utils.get_language(db) == "ru"


def test_strings_follow_language(builtin_loader):
    loader = builtin_loader
    (greeter,) = asyncio.run(loader.install(TRANSLATED, "file:greeter.py"))
    cmd = loader.get_command("hi")
    assert greeter.strings("hi", name="<x>") == "Привет, &lt;x&gt;!" and greeter.strings["only_base"] == "base"
    assert loader.module_doc(greeter) == "Здоровается" and loader.command_doc(cmd) == "— поздороваться"

    assert run(loader, ".lang en").startswith("🌐 <b>Language</b> · 🇬🇧 English")
    assert loader.db.get(MAIN_OWNER, "lang") == "en"
    assert greeter.strings("hi", name="Bob") == "Hello, Bob!"
    assert loader.module_doc(greeter) == "Greets" and loader.command_doc(cmd) == "— say hello"
    assert run(loader, ".help").startswith("📦 <b>Modules</b>")

    assert run(loader, ".lang de").startswith("❌ <b>No such language</b>")
    assert run(loader, ".lang ru").startswith("🌐 <b>Язык</b> · 🇷🇺 Русский")
    assert greeter.strings("hi", name="Bob") == "Привет, Bob!"


def test_new_modules_load_in_current_language(builtin_loader):
    loader = builtin_loader
    run(loader, ".lang en")
    (greeter,) = asyncio.run(loader.install(TRANSLATED, "file:greeter.py"))
    assert greeter.strings["hi"] == "Hello, {name}!"
    asyncio.run(loader.reload_all())
    assert "📦 <b>Modules</b>" in run(loader, ".help")


def test_hikka_strings_follow_language(builtin_loader):
    loader = builtin_loader
    (demo,) = asyncio.run(loader.install(HIKKA_DEMO, "file:demo.py"))
    assert demo.strings("hello") == "Привет, <b>{}</b>!" and demo.name == "Demo"
    run(loader, ".lang en")
    assert demo.strings("hello") == "Hello, <b>{}</b>!" and demo.strings("missing").startswith("Unknown strings")
    assert demo.name == "Demo"


def test_builtin_modules_answer_in_english(builtin_loader):
    loader = builtin_loader
    run(loader, ".lang en")
    assert run(loader, ".doctor").startswith("🩺 <b>Diagnostics</b> · all good")
    assert run(loader, ".stats").startswith("📊 <b>Statistics</b>")
    assert run(loader, ".cfg backup").startswith("⚙️ <b>Backup</b> · settings")
    assert "Auto backup every this many hours" in run(loader, ".cfg backup interval")
    assert run(loader, ".inlinebot") == "❌ <b>The inline bot is unavailable</b>"
    assert run(loader, ".aliases").startswith("🏷 <b>No aliases</b>")
    assert run(loader, ".dlm").startswith("❌ <b>Which module to install?</b>")
    assert run(loader, ".repos").startswith("📚 <b>Repos</b> · 1")
    assert run(loader, ".security flood").startswith("❄️ <b>Flood protection is on</b>")
    assert run(loader, ".ulm") == "❌ <b>Which module to remove?</b>"
