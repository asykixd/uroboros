import asyncio
from types import SimpleNamespace

import pytest
from fake_inline import OWNER_ID, STRANGER_ID, FakeMessage, button_texts, make_env, press, user

from uroboros import inline as inline_pkg
from uroboros.database import Database
from uroboros.errors import InlineError
from uroboros.inline import botfather
from uroboros.inline.manager import FOREIGN, INPUT_MARKER, OWNER, STALE, TOKEN_ENV, InlineManager, TokenRejected
from uroboros.inline.types import normalize_buttons
from uroboros.loader import Loader


@pytest.fixture
def env(tmp_path):
    env = make_env(tmp_path)
    yield env
    env.db.close()


def test_form_sends_and_calls_callback(env):
    calls = []

    async def cb(call, value, flag=False):
        calls.append((value, flag))
        await call.answer("готово")

    message = FakeMessage()
    form = asyncio.run(
        env.manager.form(
            message, "<b>Привет</b>", [[{"text": "Жми", "callback": cb, "args": (1,), "kwargs": {"flag": True}}]]
        )
    )
    assert message.deleted
    assert form.inline_message_id == f"im-{form.id}"
    result = env.bot.inline_answers[-1][0]
    assert result.input_message_content.message_text == "<b>Привет</b>"
    assert result.reply_markup.inline_keyboard[0][0].text == "Жми"

    press(env.manager, "Жми")
    assert calls == [(1, True)]
    assert env.bot.answers() == [("готово", False)]


def test_buttons_only_for_owner_and_allowed(env):
    calls = []

    async def cb(call):
        calls.append(call.from_user.id)

    asyncio.run(env.manager.form(FakeMessage(), "x", {"text": "a", "callback": cb}))
    press(env.manager, "a", user_id=STRANGER_ID)
    assert calls == [] and env.bot.answers() == [(FOREIGN, True)]

    asyncio.run(env.manager.form(FakeMessage(), "y", {"text": "b", "callback": cb}, always_allow=[STRANGER_ID]))
    press(env.manager, "b", user_id=STRANGER_ID)
    assert calls == [STRANGER_ID]


def test_unknown_button_is_stale(env):
    asyncio.run(
        env.manager._on_callback(SimpleNamespace(id="cb", data="nope", from_user=user(), inline_message_id="i"))
    )
    assert env.bot.answers() == [(STALE, False)]


def test_edit_rerenders_buttons(env):
    async def first(call):
        await call.edit("второй", [{"text": "две", "callback": second}])

    async def second(call):
        await call.edit(buttons=None)

    form = asyncio.run(env.manager.form(FakeMessage(), "первый", {"text": "раз", "callback": first}))
    press(env.manager, "раз")
    edit = env.bot.edits()[-1]
    assert edit["text"] == "второй" and edit["inline_message_id"] == form.inline_message_id
    assert button_texts(env.manager, form.unit) == ["две"]

    press(env.manager, "две")
    assert env.bot.edits()[-1]["reply_markup"] is None
    assert button_texts(env.manager, form.unit) == []


def test_error_in_callback_is_shown(env):
    async def boom(call):
        raise InlineError("Нельзя")

    asyncio.run(env.manager.form(FakeMessage(), "x", {"text": "a", "callback": boom}))
    press(env.manager, "a")
    assert env.bot.answers() == [("Нельзя", True)]


def test_confirm(env):
    calls = []

    async def remove(call):
        calls.append("removed")
        await call.edit("Удалено", None)

    form = asyncio.run(
        env.manager.form(FakeMessage(), "Модуль", {"text": "Удалить", "callback": remove, "confirm": "Точно?"})
    )
    press(env.manager, "Удалить")
    assert env.bot.edits()[-1]["text"] == "Точно?" and calls == []

    press(env.manager, "Отмена")
    assert env.bot.edits()[-1]["text"] == "Модуль"
    assert button_texts(env.manager, form.unit) == ["Удалить"]

    press(env.manager, "Удалить")
    press(env.manager, "✅ Да")
    assert calls == ["removed"] and env.bot.edits()[-1]["text"] == "Удалено"


def test_close_deletes_message(env):
    form = asyncio.run(env.manager.form(FakeMessage(), "x", {"text": "✖", "action": "close"}))
    press(env.manager, "✖")
    chat_id, message_id = form.unit.user_message
    assert env.client.deleted == [(chat_id, [message_id])]
    assert form.id not in env.manager._units


def test_input(env):
    got = []

    async def handler(call, text, key):
        got.append((key, text))
        await call.edit(f"Сохранено: {text}")

    form = asyncio.run(
        env.manager.form(
            FakeMessage(), "x", {"text": "✍️", "input": "Новое значение", "handler": handler, "args": ("k",)}
        )
    )
    key = next(iter(env.manager._inputs))
    query = SimpleNamespace(id="q", query=f"{key} привет", from_user=user())
    asyncio.run(env.manager._on_inline_query(query))
    article = env.bot.inline_answers[-1][0]
    assert article.id == key and article.title == "Новое значение" and article.description == "привет"
    assert article.input_message_content.message_text == INPUT_MARKER

    chosen = SimpleNamespace(result_id=key, from_user=user(), query=f"{key} привет", inline_message_id=None)
    asyncio.run(env.manager._on_chosen(chosen))
    assert got == [("k", "привет")]
    edit = env.bot.edits()[-1]
    assert edit["text"] == "Сохранено: привет" and edit["inline_message_id"] == form.inline_message_id


def test_list_pages(env):
    form = asyncio.run(env.manager.list(FakeMessage(), ["один", "два", "три"]))
    assert "1/3" in button_texts(env.manager, form.unit)
    press(env.manager, "▶")
    assert env.bot.edits()[-1]["text"] == "два"
    press(env.manager, "◀")
    press(env.manager, "◀")
    assert env.bot.edits()[-1]["text"] == "три"
    assert "3/3" in button_texts(env.manager, form.unit)


def test_gallery(env):
    form = asyncio.run(env.manager.gallery(FakeMessage(), ["https://e/1.jpg", "https://e/2.jpg"], "подпись"))
    assert env.bot.inline_answers[-1][0].photo_url == "https://e/1.jpg"
    press(env.manager, "▶")
    edit = env.bot.edits()[-1]
    assert edit["media"].media == "https://e/2.jpg" and edit["media"].caption == "подпись"
    assert form.unit.photo == "https://e/2.jpg"

    urls = iter(["https://e/a.jpg", "https://e/b.jpg"])

    async def next_photo():
        return next(urls)

    asyncio.run(env.manager.gallery(FakeMessage(), next_photo))
    assert env.bot.inline_answers[-1][0].photo_url == "https://e/a.jpg"
    press(env.manager, "Ещё ▶")
    assert env.bot.edits()[-1]["media"].media == "https://e/b.jpg"


def test_stranger_inline_query_gets_nothing(env):
    form = asyncio.run(env.manager.form(FakeMessage(), "секрет", {"text": "a", "callback": lambda c: None}))
    asyncio.run(env.manager._on_inline_query(SimpleNamespace(id="q", query=form.id, from_user=user(STRANGER_ID))))
    assert env.bot.inline_answers[-1] == []


MODULE = '''
from uroboros import Module, callback_handler, command, inline_handler

class Buttons(Module):
    """Кнопки"""

    pressed = []

    @command("buttons")
    async def buttons(self, message):
        buttons = [{"text": "Жми", "callback": self.press}, {"text": "Данные", "data": "demo:1"}]
        await self.inline.form(message, "Форма", buttons)

    async def press(self, call):
        self.pressed.append("press")

    @callback_handler("demo:")
    async def on_data(self, call):
        self.pressed.append(call.data)

    @inline_handler()
    async def echo_inline_handler(self, query):
        """— повторить текст"""
        return {"title": "Эхо", "message": query.args or "пусто", "buttons": [{"text": "Ок", "callback": self.press}]}
'''


def test_module_api_and_unload(env):
    (inst,) = asyncio.run(env.loader.install(MODULE, "file:buttons.py"))
    assert inst.inline.available and inst.inline.bot_username == "testbot"
    asyncio.run(env.loader.get_command("buttons").func(FakeMessage()))
    press(env.manager, "Жми")
    assert inst.pressed == ["press"]

    data_query = SimpleNamespace(id="cb", data="demo:1", from_user=user(), inline_message_id="im-x", message=None)
    asyncio.run(env.manager._on_callback(data_query))
    assert inst.pressed == ["press", "demo:1"]

    asyncio.run(env.manager._on_inline_query(SimpleNamespace(id="q", query="echo привет", from_user=user())))
    result = env.bot.inline_answers[-1][0]
    assert result.title == "Эхо" and result.input_message_content.message_text == "привет"

    asyncio.run(env.manager._on_inline_query(SimpleNamespace(id="q", query="", from_user=user())))
    assert [r.title for r in env.bot.inline_answers[-1]] == ["echo"]

    asyncio.run(env.loader.uninstall("Buttons"))
    assert env.manager._units == {} and env.manager._buttons == {}
    assert env.loader.inline_handlers == {} and env.loader.callback_handlers == []
    asyncio.run(env.manager._on_callback(data_query))
    assert env.bot.answers()[-1] == (STALE, False)


def test_inline_handler_name_conflict(env):
    asyncio.run(env.loader.install(MODULE, "file:buttons.py"))
    other = MODULE.replace("class Buttons", "class Other").replace('"buttons"', '"other"')
    with pytest.raises(Exception, match="Inline-команда echo уже занята"):
        asyncio.run(env.loader.install(other, "file:other.py"))


def test_inline_unavailable(tmp_path):
    db = Database(":memory:")
    loader = Loader(None, db, tmp_path)
    proxy = inline_pkg.Inline(loader, None)
    assert not proxy.available
    with pytest.raises(InlineError, match="не запущен"):
        asyncio.run(proxy.form(FakeMessage(), "x"))

    manager = InlineManager(None, db)
    manager.error = "нет токена"
    loader.inline = manager
    with pytest.raises(InlineError, match="нет токена"):
        asyncio.run(proxy.form(FakeMessage(), "x"))
    db.close()


@pytest.mark.parametrize(
    "buttons",
    [
        [{"callback": print}],
        [{"text": "a"}],
        [{"text": "a", "url": "https://e", "callback": print}],
        [{"text": "a", "input": "?"}],
        [{"text": "a", "action": "explode"}],
        [{"text": "a", "data": "x" * 65}],
    ],
)
def test_invalid_buttons(buttons):
    with pytest.raises(InlineError):
        normalize_buttons(buttons)


def test_button_shapes():
    one = {"text": "a", "url": "https://e"}
    assert normalize_buttons(one) == [[one]]
    assert normalize_buttons([one, one]) == [[one, one]]
    assert normalize_buttons([[one], [one]]) == [[one], [one]]
    assert normalize_buttons(None) == []


class FakeConversation:
    def __init__(self, replies):
        self.replies = list(replies)
        self.sent = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def send_message(self, text):
        self.sent.append(text)

    async def get_response(self):
        return SimpleNamespace(raw_text=self.replies.pop(0))


class BotFatherClient:
    def __init__(self, replies):
        self.conv = FakeConversation(replies)

    def conversation(self, *args, **kwargs):
        return self.conv


TOKEN = "123456789:AAH" + "x" * 32


def test_botfather_create_bot_retries_taken_username():
    client = BotFatherClient(
        [
            "No active command to cancel.",
            "Alright, a new bot. How are we going to call it? Please choose a name for your bot.",
            "Good. Now let's choose a username for your bot.",
            "Sorry, this username is already taken. Please try something different.",
            f"Done! Congratulations on your new bot. Use this token to access the HTTP API:\n{TOKEN}\nKeep it secure",
        ]
    )
    assert asyncio.run(botfather.create_bot(client)) == TOKEN
    usernames = client.conv.sent[3:]
    assert len(usernames) == 2 and all(u.startswith("uroboros_") and u.endswith("_bot") for u in usernames)


def test_botfather_limit_is_reported():
    client = BotFatherClient(["ok", "That I cannot do. You come to me asking for more than 20 bots."])
    with pytest.raises(InlineError, match="20 bots"):
        asyncio.run(botfather.create_bot(client))


def test_botfather_setup_inline():
    client = BotFatherClient(
        [
            "ok",
            "Choose a bot to change inline queries status.",
            "This will enable inline queries for your bot. Please send me the placeholder message.",
            "Success! Inline settings updated.",
            "Choose a bot to change inline feedback settings.",
            "Inline feedback ... Current status: Disabled.",
            "Success! Inline settings updated.",
        ]
    )
    asyncio.run(botfather.setup_inline(client, "my_bot"))
    assert client.conv.sent == [
        "/cancel",
        "/setinline",
        "@my_bot",
        "Uroboros",
        "/setinlinefeedback",
        "@my_bot",
        "Enabled",
    ]


def start_env(monkeypatch, valid_tokens):
    db = Database(":memory:")
    manager = InlineManager(None, db)
    manager.owner_id = OWNER_ID
    started = []

    async def fake_run(token):
        if token not in valid_tokens:
            raise TokenRejected("Токен бота недействителен")
        started.append(token)

    async def fake_create(client):
        return "new-token"

    monkeypatch.setattr(manager, "_run", fake_run)
    monkeypatch.setattr(manager, "stop", lambda: asyncio.sleep(0))
    monkeypatch.setattr(manager, "_check_token", lambda token: asyncio.sleep(0, SimpleNamespace(username="b")))
    monkeypatch.setattr(botfather, "create_bot", fake_create)
    return manager, started


def test_start_recreates_revoked_bot(monkeypatch):
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    manager, started = start_env(monkeypatch, {"new-token"})
    manager.db.set(OWNER, "token", "old-token")
    asyncio.run(manager.start())
    assert started == ["new-token"] and manager.db.get(OWNER, "token") == "new-token"


def test_start_keeps_env_token(monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, "env-token")
    manager, started = start_env(monkeypatch, {"new-token"})
    asyncio.run(manager.start())
    assert started == [] and "недействителен" in manager.error
    with pytest.raises(InlineError, match=TOKEN_ENV):
        asyncio.run(manager.set_token("x"))


def test_start_disabled(monkeypatch):
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    manager, started = start_env(monkeypatch, {"new-token"})
    asyncio.run(manager.disable())
    asyncio.run(manager.start())
    assert started == [] and "off" in manager.error
    asyncio.run(manager.enable())
    assert started == ["new-token"] and manager.error is None
