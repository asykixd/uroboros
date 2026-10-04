import asyncio
import sys
from types import SimpleNamespace

from conftest import FakeMessage

from uroboros.database import MAIN_OWNER
from uroboros.dispatcher import Dispatcher


class Message(FakeMessage):
    async def get_reply_message(self):
        return None


def run(loader, text):
    message = Message(text)
    asyncio.run(loader.get_command(text.split()[0][1:]).func(message))
    return message.edits[-1]


def test_prefix_and_aliases(builtin_loader):
    loader = builtin_loader
    assert "❌" in run(loader, ".setprefix toolong")
    assert run(loader, ".setprefix !").startswith("⌨️ <b>Префикс</b> <code>!</code>")
    assert loader.db.get(MAIN_OWNER, "prefix") == "!"

    assert "→ <code>help</code>" in run(loader, ".alias h help")
    assert "❌" in run(loader, ".alias x nope")
    assert "уже команда" in run(loader, ".alias ping help")
    assert "<code>h</code> → <code>help</code>" in run(loader, ".aliases")
    assert "удалён" in run(loader, ".unalias h")
    assert run(loader, ".aliases").startswith("🏷 <b>Алиасов нет</b>")


def test_dispatcher_resolves_user_alias_and_reports_errors(builtin_loader):
    loader = builtin_loader
    loader.db.set(MAIN_OWNER, "aliases", {"h": "help"})
    dispatcher = Dispatcher(None, loader.db, loader)
    message = Message(".h")
    asyncio.run(dispatcher._on_message(SimpleNamespace(message=message)))
    assert message.edits[-1].startswith("📦 <b>Модули</b>")

    message = Message(".e 1/0")
    asyncio.run(dispatcher._on_message(SimpleNamespace(message=message)))
    assert "ZeroDivisionError" in message.edits[-1]

    message = Message(".help")
    message.out = False
    message.sender_id = 999
    asyncio.run(dispatcher._on_message(SimpleNamespace(message=message)))
    assert message.edits == []  # чужая команда без прав — молча игнорируется


def test_eval(builtin_loader):
    text = run(builtin_loader, ".e print('hi'); 40 + 2")
    assert "hi" in text
    assert "<pre>42</pre>" in run(builtin_loader, ".e 40 + 2")
    assert "await работает" in run(builtin_loader, ".e await asyncio.sleep(0, 'await работает')")
    assert "Ошибка" in run(builtin_loader, ".e undefined_name")


def test_terminal(builtin_loader):
    text = run(builtin_loader, f'.t "{sys.executable}" -c "print(123)"')
    assert "123" in text and "<code>0</code>" in text


class FakeManager:
    def __init__(self):
        self.ready = False
        self.error = "нет токена"
        self.bot_username = None
        self.token_from_env = False
        self.calls = []

    async def disable(self):
        self.calls.append("off")

    async def enable(self):
        self.calls.append("on")
        self.ready, self.bot_username = True, "my_bot"

    async def create_bot(self):
        self.calls.append("new")

    async def set_token(self, token):
        self.calls.append(token)


def test_inlinebot_command(builtin_loader):
    loader = builtin_loader
    assert run(loader, ".inlinebot") == "❌ <b>Inline-бот недоступен</b>"
    loader.inline = FakeManager()
    assert "нет токена" in run(loader, ".inlinebot")
    assert "выключен" in run(loader, ".inlinebot off")
    assert "@my_bot" in run(loader, ".inlinebot on")
    run(loader, ".inlinebot 123:abc")
    run(loader, ".inlinebot new")
    assert "❌" in run(loader, ".inlinebot something")
    assert loader.inline.calls == ["off", "on", "123:abc", "new"]
