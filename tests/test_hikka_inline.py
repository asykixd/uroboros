import asyncio
from types import SimpleNamespace

import pytest
from fake_inline import FakeMessage, make_env, press, user

from uroboros.hikka import inline_adapter as ia
from uroboros.inline import Inline


@pytest.fixture
def env(tmp_path):
    env = make_env(tmp_path)
    module = SimpleNamespace(_stem="hikkamod", name="HikkaMod")
    env.hikka = ia.HikkaInline(Inline(env.loader, module))
    yield env
    env.db.close()


def test_properties_and_generate_markup(env):
    assert env.hikka.bot is env.bot and env.hikka.bot_username == "testbot" and env.hikka.init_complete
    assert env.hikka.generate_markup(None) is None and env.hikka.generate_markup("unit") is None
    markup = env.hikka.generate_markup([{"text": "url", "url": "https://e"}])
    assert markup.inline_keyboard[0][0].url == "https://e"
    assert env.hikka.generate_markup(markup) is markup


def test_form_with_chat_id_and_actions(env):
    form = asyncio.run(
        env.hikka.form(
            "Текст",
            12345,
            reply_markup=[[{"text": "Снять", "action": "unload"}], [{"text": "Закрыть", "action": "close"}]],
            disable_security=True,
        )
    )
    assert isinstance(form, ia.HikkaInlineMessage) and form.unit_id
    press(env.manager, "Снять", user_id=7)  # disable_security: может нажать кто угодно
    assert env.manager._buttons == {}


def test_hikka_call_api(env):
    seen = {}

    async def cb(call):
        seen["data"] = call.data
        seen["user"] = call.from_user.id
        seen["form"] = call.form["text"]
        seen["unit"] = call.unit_id
        seen["inline_id"] = call.inline_message_id
        seen["raw"] = call.id  # из CallbackQuery
        await call.answer("ок", True)
        assert await call.edit("новое", reply_markup={"text": "ещё", "callback": cb2})

    async def cb2(call):
        await call.unload()

    asyncio.run(env.hikka.form("Форма", FakeMessage(), reply_markup={"text": "Жми", "callback": cb}))
    press(env.manager, "Жми")
    assert seen["user"] == 42 and seen["form"] == "Форма" and seen["raw"] == "cb" and seen["inline_id"]
    assert env.bot.answers()[0] == ("ок", True)
    press(env.manager, "ещё")
    assert env.manager._buttons == {}


def test_inline_message_edit_delete(env):
    form = asyncio.run(env.hikka.form("Форма", FakeMessage(), reply_markup={"text": "a", "url": "https://e"}))
    assert asyncio.run(form.edit("изменено")) is form
    assert env.bot.edits()[-1]["text"] == "изменено"
    assert asyncio.run(form.delete()) is True and env.client.deleted


def test_failures_return_false(env):
    env.manager.bot = None
    assert asyncio.run(env.hikka.form("x", FakeMessage())) is False
    assert asyncio.run(env.hikka.list(FakeMessage(), ["a"])) is False


def test_list_and_gallery(env):
    asyncio.run(env.hikka.list(FakeMessage(), ["один", "два"], custom_buttons=[{"text": "доп", "url": "https://e"}]))
    press(env.manager, "▶")
    assert env.bot.edits()[-1]["text"] == "два"

    asyncio.run(env.hikka.gallery(FakeMessage(), lambda: ["https://e/1.jpg"], caption=lambda: "подпись"))
    assert env.bot.inline_answers[-1][0].photo_url == "https://e/1.jpg"
    assert env.bot.inline_answers[-1][0].caption == "подпись"


def test_inline_query_wrapper():
    answered = []

    async def answer(results, **kwargs):
        answered.append((results, kwargs))

    raw = SimpleNamespace(query="echo hi", from_user=user(), id="q", answer=answer)
    from uroboros.inline.types import InlineQuery

    ours = InlineQuery(raw, "hi")
    query = ia.HikkaInlineQuery(ours)
    assert query.args == "hi" and query.query == "echo hi" and query.id == "q" and query.inline_query is raw
    asyncio.run(query.e404())
    assert ours.answered and answered[0][0][0].title == "Ничего не найдено"
    assert answered[0][1] == {"cache_time": 0, "is_personal": True}


def test_convert_inline_results():
    assert ia.convert_inline_results(None) is None
    (item,) = ia.convert_inline_results(
        {
            "title": "t",
            "message": "m",
            "reply_markup": {"text": "u", "url": "https://e"},
            "gif": "g",
            "disable_security": 1,
        }
    )
    assert item["buttons"] == [[{"text": "u", "url": "https://e"}]] and item["photo"] == "g" and item["public"]


def test_sanitise_text(env):
    assert env.hikka.sanitise_text('<emoji document_id="1">🔥</emoji> текст') == "🔥 текст"
    asyncio.run(env.hikka.form('<emoji document_id="1">🔥</emoji>', FakeMessage()))
    assert env.bot.inline_answers[-1][0].input_message_content.message_text == "🔥"
