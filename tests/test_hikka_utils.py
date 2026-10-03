import asyncio
from types import SimpleNamespace

import pytest
from conftest import FakeMessage
from fake_inline import make_env, press

from uroboros.hikka import inline_adapter, state
from uroboros.hikka import utils as hutils


def msg(text="", chat_id=-1001234567890, **kw):
    m = FakeMessage(text)
    m.chat_id = chat_id
    for key, value in kw.items():
        setattr(m, key, value)
    return m


def test_args_helpers():
    m = msg('.cmd a, b ,, c "d e"')
    m.text = ".cmd <b>a</b>, b"
    assert hutils.get_args_split_by(m, ",") == ["a", "b", 'c "d e"']
    assert hutils.get_args(m) == ["a,", "b", ",,", "c", "d e"]
    assert hutils.get_args_html(m) == "<b>a</b>, b"
    assert hutils.get_chat_id(m) == 1234567890


def test_text_helpers():
    assert hutils.escape_quotes('<a href="x">') == "&lt;a href=&quot;x&quot;&gt;"
    assert hutils.remove_html("<b>a&amp;b</b>") == "a&b"
    assert hutils.remove_html("<b><i></b>", escape=True) == ""
    assert hutils.check_url("https://example.com") and not hutils.check_url("nope")
    assert len(hutils.rand(12)) == 12
    assert hutils.get_lang_flag("ru") == "🇷🇺" and hutils.get_lang_flag("xyz") == "xyz"
    assert hutils.chunks([1, 2, 3], 2) == [[1, 2], [3]]
    assert hutils.array_sum([[1], [2, 3]]) == [1, 2, 3]
    assert list(hutils.smart_split("aaa\nbbb\nccc", length=8)) == ["aaa\nbbb", "ccc"]
    assert list(hutils.smart_split("x" * 10, length=4)) == ["xxxx", "xxxx", "xx"]
    assert hutils.merge({"a": {"b": 1}, "l": [2]}, {"a": {"c": 2}, "l": [1]}) == {"a": {"c": 2, "b": 1}, "l": [1, 2]}
    assert ":" in hutils.formatted_uptime() and hutils.uptime() >= 0
    assert hutils.is_serializable({"a": 1}) and not hutils.is_serializable(object())
    assert hutils.get_platform_emoji() == "🐍" and hutils.ascii_face()


def test_entity_links():
    user = SimpleNamespace(id=5, first_name="A", username="a")
    channel = SimpleNamespace(id=7, username=None)
    assert hutils.get_link(user) == "tg://user?id=5"
    assert hutils.get_link(SimpleNamespace(id=7, username="chan")) == "https://t.me/chan"
    assert hutils.get_entity_url(user) == "https://t.me/a"
    assert hutils.get_entity_url(SimpleNamespace(id=5, first_name="A", username=None), openmessage=True).startswith(
        "tg://openmessage"
    )
    assert hutils.get_entity_url(channel) == "https://t.me/c/7"

    async def get_chat():
        return SimpleNamespace(username=None)

    m = msg(id=3)
    m.get_chat = get_chat
    assert asyncio.run(hutils.get_message_link(m)) == "https://t.me/c/1234567890/3"


def test_relocate_entities_and_mime():
    ent = SimpleNamespace(offset=2, length=10)
    hutils.relocate_entities([ent], -4, "abcdef")
    assert (ent.offset, ent.length) == (0, 6)
    assert hutils.mime_type(SimpleNamespace(file=SimpleNamespace(mime_type="image/png"))) == "image/png"
    assert hutils.mime_type(SimpleNamespace(file=None)) == ""


def test_answer_with_markup_and_file(tmp_path, monkeypatch):
    env = make_env(tmp_path)
    state.loader = env.loader
    sent = []

    async def fake_answer_file(message, file, caption=None, **kwargs):
        sent.append((file, caption))

    monkeypatch.setattr("uroboros.utils.answer_file", fake_answer_file)
    calls = []

    async def cb(call):
        calls.append(call.data)

    from fake_inline import FakeMessage as InlineMessage

    result = asyncio.run(hutils.answer(InlineMessage(), "Форма", reply_markup=[{"text": "Жми", "callback": cb}]))
    assert isinstance(result, inline_adapter.HikkaInlineMessage)
    press(env.manager, "Жми")
    assert len(calls) == 1

    asyncio.run(hutils.answer(msg(), "подпись", file="x.png"))
    assert sent == [("x.png", "подпись")]
    env.db.close()


def test_get_target(monkeypatch):
    async def fake_target(message, arg=None):
        from telethon.tl.types import User

        return User(id=99) if arg == "@u" or message.is_reply else None

    monkeypatch.setattr("uroboros.utils.get_target", fake_target)
    m = msg(".x @u", is_reply=False, is_private=False)
    assert asyncio.run(hutils.get_target(m)) == 99
    m = msg(".x", is_reply=False, is_private=False)
    assert asyncio.run(hutils.get_target(m)) is None


def test_unsupported_names():
    for name in ("find_caller", "asset_forum_topic", "something_new"):
        with pytest.raises(AttributeError, match="не поддерживается"):
            getattr(hutils, name)
