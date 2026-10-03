"""Заглушки бота и юзербота для тестов inline-форм: без сети и без aiogram-опроса."""

import asyncio
from types import SimpleNamespace

from uroboros.database import Database
from uroboros.inline.manager import InlineManager
from uroboros.loader import Loader

OWNER_ID = 42
STRANGER_ID = 7


class FakeBot:
    def __init__(self):
        self.calls = []
        self.inline_answers = []

    async def answer_inline_query(self, query_id, results, **kwargs):
        self.inline_answers.append(results)

    async def answer_callback_query(self, query_id, text=None, show_alert=False):
        self.calls.append(("answer", text, show_alert))

    async def edit_message_text(self, **kwargs):
        self.calls.append(("edit_text", kwargs))

    async def edit_message_caption(self, **kwargs):
        self.calls.append(("edit_caption", kwargs))

    async def edit_message_media(self, **kwargs):
        self.calls.append(("edit_media", kwargs))

    def edits(self):
        return [call[1] for call in self.calls if call[0].startswith("edit")]

    def answers(self):
        return [(call[1], call[2]) for call in self.calls if call[0] == "answer"]


def user(user_id=OWNER_ID):
    return SimpleNamespace(id=user_id)


class FakeClient:
    """Юзербот: inline-запрос к своему боту и отправка результата в чат."""

    def __init__(self):
        self.manager = None
        self.deleted = []
        self.sent = 0

    async def inline_query(self, bot, query):
        await self.manager._on_inline_query(SimpleNamespace(id="q", query=query, from_user=user()))
        results = self.manager.bot.inline_answers[-1]
        return [FakeResult(self, r) for r in results]

    async def delete_messages(self, chat, ids):
        self.deleted.append((chat, ids))

    def add_event_handler(self, *args):
        pass

    def remove_event_handler(self, *args):
        pass


class FakeResult:
    def __init__(self, client, result):
        self.client = client
        self.result = result

    async def click(self, chat_id, reply_to=None):
        self.client.sent += 1
        # Как Telegram с включённым inline feedback: бот узнаёт inline_message_id.
        await self.client.manager._on_chosen(
            SimpleNamespace(
                result_id=self.result.id, from_user=user(), query="", inline_message_id=f"im-{self.result.id}"
            )
        )
        return SimpleNamespace(chat_id=chat_id, id=100 + self.client.sent)


class FakeMessage:
    """Своё сообщение с командой: форма заменяет его, текстовый ответ — редактирует."""

    out = True
    chat_id = 5
    id = 10
    reply_to_msg_id = None

    def __init__(self, text=""):
        self.raw_text = text
        self.deleted = False
        self.edits = []

    async def delete(self):
        self.deleted = True

    async def edit(self, text, **kwargs):
        self.edits.append(text)
        return self


def make_env(tmp_path, *, builtins=False):
    db = Database(":memory:")
    client = FakeClient()
    loader = Loader(None, db, tmp_path / "modules")
    manager = InlineManager(client, db)
    client.manager = manager
    manager.loader = loader
    loader.inline = manager
    manager.bot, manager.bot_username, manager.bot_id, manager.owner_id = FakeBot(), "testbot", 1, OWNER_ID
    if builtins:
        asyncio.run(loader.load_all())
    return SimpleNamespace(db=db, client=client, loader=loader, manager=manager, bot=manager.bot)


def press(manager, text, user_id=OWNER_ID, unit=None):
    """Нажимает кнопку с этим текстом в последней разметке формы."""
    units = [unit] if unit else list(manager._units.values())
    for key, (u, button) in list(manager._buttons.items()):
        if button["text"] == text and u in units:
            query = SimpleNamespace(id="cb", data=key, from_user=user(user_id), inline_message_id=u.inline_message_id)
            return asyncio.run(manager._on_callback(query))
    raise AssertionError(f"Нет кнопки {text!r}")


def button_texts(manager, unit):
    return sorted(b["text"] for u, b in manager._buttons.values() if u is unit)


def type_input(manager, unit, text):
    """Ввод текста в кнопку ввода формы: выбор результата ``@бот <id> текст``."""
    key = next(k for k, (u, _) in manager._inputs.items() if u is unit)
    query = f"{key} {text}"
    asyncio.run(manager._on_inline_query(SimpleNamespace(id="q", query=query, from_user=user())))
    chosen = SimpleNamespace(result_id=key, from_user=user(), query=query, inline_message_id=None)
    asyncio.run(manager._on_chosen(chosen))
