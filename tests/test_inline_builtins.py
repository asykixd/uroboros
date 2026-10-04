import asyncio

import pytest
from fake_inline import FakeMessage, button_texts, make_env, press, type_input

CONFIGURED = """
from uroboros import ConfigValue, Module, ModuleConfig, validators

class Tuned(Module):
    def __init__(self):
        self.config = ModuleConfig(
            ConfigValue("count", 1, "Сколько", validators.Integer(minimum=1)),
            ConfigValue("loud", False, "Громко", validators.Boolean()),
            ConfigValue("mode", "a", "Режим", validators.Choice(["a", "b"])),
        )
"""


@pytest.fixture
def env(tmp_path):
    env = make_env(tmp_path, builtins=True)
    yield env
    env.db.close()


def run(env, text):
    message = FakeMessage(text)
    asyncio.run(env.loader.get_command(text.split()[0][1:]).func(message))
    return message


def last_unit(env):
    return list(env.manager._units.values())[-1]


def last_text(env):
    edits = env.bot.edits()
    return edits[-1]["text"] if edits else env.bot.inline_answers[-1][0].input_message_content.message_text


def test_help_pages_and_module(env):
    for i in range(12):
        source = f"from uroboros import Module\nclass Extra{i:02}(Module):\n    pass\n"
        asyncio.run(env.loader.install(source, f"file:extra{i}.py"))
    message = run(env, ".help")
    assert message.deleted and message.edits == []
    unit = last_unit(env)
    assert "1/2" in button_texts(env.manager, unit) and "Config" in button_texts(env.manager, unit)

    press(env.manager, "▶")
    assert "Extra" in last_text(env) and "2/2" in button_texts(env.manager, unit)

    name = next(t for t in button_texts(env.manager, unit) if t.startswith("Extra"))
    press(env.manager, name)
    assert f"📦 <b>{name}</b>" in last_text(env)
    press(env.manager, "◀ Назад")
    assert "2/2" in button_texts(env.manager, unit)


def test_help_with_argument_is_text(env):
    message = run(env, ".help help")
    assert not message.deleted and message.edits[-1].startswith("📦 <b>Help</b>")


def test_cfg_inline(env):
    (tuned,) = asyncio.run(env.loader.install(CONFIGURED, "file:tuned.py"))
    run(env, ".cfg")
    unit = last_unit(env)
    assert "Tuned" in button_texts(env.manager, unit)

    press(env.manager, "Tuned")
    assert {"count", "loud", "mode"} <= set(button_texts(env.manager, unit))

    press(env.manager, "loud")
    press(env.manager, "Включить")
    assert tuned.config["loud"] is True and "✅ Сохранено" in last_text(env)
    assert "Выключить" in button_texts(env.manager, unit)

    press(env.manager, "◀ Назад")
    press(env.manager, "mode")
    press(env.manager, "b")
    assert tuned.config["mode"] == "b"
    press(env.manager, "↩️ Сбросить")
    assert tuned.config["mode"] == "a"

    run(env, ".cfg tuned count")
    unit = last_unit(env)
    type_input(env.manager, unit, "0")
    assert tuned.config["count"] == 1 and "❌ Минимум — 1" in last_text(env)
    type_input(env.manager, unit, "3")
    assert tuned.config["count"] == 3 and "✅ Сохранено" in last_text(env)


def test_cfg_with_value_is_text(env):
    (tuned,) = asyncio.run(env.loader.install(CONFIGURED, "file:tuned.py"))
    message = run(env, ".cfg tuned count 2")
    assert tuned.config["count"] == 2 and message.edits[-1].startswith("✅")


def test_ulm_asks_confirmation(env):
    asyncio.run(env.loader.install("from uroboros import Module\nclass Doomed(Module):\n    pass\n", "file:d.py"))
    run(env, ".ulm doomed")
    assert env.loader.get_module("doomed") is not None
    assert "Удалить <b>Doomed</b>?" in last_text(env)

    press(env.manager, "🗑 Удалить")
    assert env.loader.get_module("doomed") is None
    assert last_text(env) == "🗑 Удалено: <b>Doomed</b>"


def test_text_fallback_without_bot(env):
    env.loader.inline = None
    message = run(env, ".help")
    assert not message.deleted and message.edits[-1].startswith("📦 <b>Модули</b>")


def test_dlm_confirmation_button(env, monkeypatch):
    from uroboros import download

    async def fake_download(url):
        return b"from uroboros import Module\nclass Remote(Module):\n    pass\n"

    monkeypatch.setattr(download, "download", fake_download)
    run(env, ".dlm https://example.com/remote.py")
    assert "Установить модуль?" in last_text(env) and env.loader.get_module("remote") is None
    press(env.manager, "✅ Установить")
    assert env.loader.get_module("remote") is not None
    assert last_text(env).startswith("✅ Модуль <b>Remote</b> загружен")


def test_uplm_confirmation_button(env, monkeypatch):
    from uroboros import download

    old = b"from uroboros import Module\nclass Remote(Module):\n    pass\n"
    asyncio.run(env.loader.install(old.decode(), "https://example.com/remote.py"))

    async def fake_download(url):
        return old.replace(b"pass", b"x = 1")

    monkeypatch.setattr(download, "download", fake_download)
    run(env, ".uplm")
    assert "Обновить модули?" in last_text(env) and "+    x = 1" in last_text(env)
    press(env.manager, "✅ Обновить")
    assert last_text(env).startswith("✅ <b>Модули обновлены")
    assert "x = 1" in (env.loader.modules_dir / "remote.py").read_text()
