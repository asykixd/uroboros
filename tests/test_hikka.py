import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import FakeMessage
from fake_inline import make_env, press, user

from uroboros.database import Database
from uroboros.dispatcher import Dispatcher
from uroboros.errors import LoadError
from uroboros.hikka import validators
from uroboros.loader import Loader

DEMO = (Path(__file__).parent / "hikka" / "demo.py").read_text("utf-8")


@pytest.fixture
def env(tmp_path):
    env = make_env(tmp_path, builtins=True)
    env.loader.security.me_id = 42
    yield env
    env.db.close()


def install(env, source=DEMO):
    (inst,) = asyncio.run(env.loader.install(source, "file:demo.py"))
    return inst


def run(env, text):
    message = FakeMessage(text)
    message.chat_id, message.id, message.reply_to_msg_id = 5, 10, None
    asyncio.run(env.loader.get_command(text.split()[0][1:]).func(message))
    return message


def test_module_loads_with_hikka_api(env):
    inst = install(env)
    assert inst.name == "Demo" and type(inst).__doc__ == "Демо-модуль"
    assert inst._meta == {"developer": "@someone", "version": "1.2.0"}
    assert inst.ready_args[1] is inst.db and inst.get("ready") is True
    assert env.db.get("DemoMod", "ready") is True  # Hikka хранит данные под именем класса

    commands = {cmd.name: cmd for cmd in env.loader.module_commands(inst)}
    assert set(commands) == {"hi", "pong", "secret", "public", "form"}
    assert commands["hi"].info.doc == "[имя] — поздороваться" and commands["hi"].info.aliases == ("hello",)
    assert commands["pong"].info.doc == "Legacy command"
    assert commands["hi"].info.access == "owner"  # по умолчанию в Hikka — только владелец
    assert commands["public"].info.access == "everyone"


def test_commands_strings_and_config(env):
    inst = install(env)
    assert run(env, ".hi Аня").edits[-1] == "Привет, <b>Аня</b>!"
    assert run(env, ".pong").edits[-1] == "pong"

    inst.config["times"] = "2"
    inst.config["loud"] = "True"
    assert inst.config["times"] == 2 and inst.config["loud"] is True
    assert run(env, ".hello x").edits[-1] == "ПРИВЕТ, <B>X</B>!" * 2
    with pytest.raises(validators.ValidationError):
        inst.config["times"] = "7"
    inst.config["names"] = "a, b"
    assert inst.config["names"] == ["a", "b"]
    assert inst.config.getdoc("times") == "Сколько раз" and inst.config.getdef("times") == 1
    assert inst.config["missing"] is None

    message = run(env, ".cfg demo times 3")
    assert inst.config["times"] == 3 and message.edits[-1].startswith("✅")


def test_watcher_tags(env):
    inst = install(env)
    dispatcher = Dispatcher(None, env.db, env.loader)

    def deliver(text, private=True):
        message = FakeMessage(text)
        message.is_private, message.out = private, False
        message.sender_id = 7
        asyncio.run(dispatcher._on_message(SimpleNamespace(message=message)))

    deliver("привет")
    deliver("в группе", private=False)
    deliver(".hi команда")
    assert inst.seen == ["привет"]


def test_loop_and_stop_loop(env):
    async def scenario():
        (inst,) = await env.loader.install(DEMO, "file:demo.py")
        for _ in range(100):
            await asyncio.sleep(0.01)
            if not inst.ticker.status:
                break
        await env.loader.uninstall("Demo")
        return inst

    inst = asyncio.run(scenario())
    assert inst.get("ticks") == 2 and not inst.ticker.status


def test_inline_form_and_callbacks(env):
    install(env)
    run(env, ".form")
    press(env.manager, "Ответ")
    assert env.bot.answers()[-1] == ("Готово", True)
    press(env.manager, "Жми")
    # Как в Hikka: edit без reply_markup убирает кнопки.
    assert env.bot.edits()[-1]["text"] == "Нажато 5" and env.bot.edits()[-1]["reply_markup"] is None


def test_inline_handler(env):
    install(env)
    query = SimpleNamespace(id="q", query="echo привет", from_user=user())
    asyncio.run(env.manager._on_inline_query(query))
    result = env.bot.inline_answers[-1][0]
    assert result.title == "Эхо" and result.input_message_content.message_text == "привет"
    assert result.reply_markup.inline_keyboard[0][0].text == "Ок"


def test_unload_removes_everything(env):
    async def scenario():
        await env.loader.install(DEMO, "file:demo.py")
        await env.loader.uninstall("Demo")

    asyncio.run(scenario())
    assert env.loader.get_command("hi") is None and env.loader.inline_handlers == {}


@pytest.mark.parametrize(
    ("source", "error"),
    [
        ("import hikka\n", "ядро Hikka"),
        ("from ..database import Database\n", r"\.\.database"),
        ("from .. import loader, database\n", "database"),
        ("from .. import loader\n# scope: hikka_only\n", "только для Hikka"),
        ("from .. import loader\n# scope: hikka_min 9.0.0\n", "Hikka 9.0.0"),
        ("import pyrogram\nfrom .. import loader\n", "Pyrogram"),
    ],
)
def test_unsupported_features_are_reported(tmp_path, source, error):
    loader = Loader(None, Database(":memory:"), tmp_path)
    src = source + "raise SystemExit('код не должен выполняться')\n"
    with pytest.raises(LoadError, match=error):
        asyncio.run(loader.install(src, "x"))


def test_unknown_utils_give_clear_error():
    from uroboros.hikka import utils

    with pytest.raises(AttributeError, match="не поддерживается Uroboros"):
        utils.asset_channel  # noqa: B018


def test_ftg_legacy_config_and_client_ready_without_args(tmp_path):
    source = """
from .. import loader, utils

class LegacyMod(loader.Module):
    strings = {"name": "Legacy"}

    def __init__(self):
        self.config = loader.ModuleConfig("KEY", "v", lambda m: "Описание")
        self.ready = False

    async def client_ready(self):
        self.ready = True

    async def legacycmd(self, message):
        await utils.answer(message, self.config["KEY"])
"""

    async def scenario():
        loader = Loader(None, Database(":memory:"), tmp_path)
        (inst,) = await loader.install(source, "x")
        assert inst.ready and inst.config["KEY"] == "v" and inst.config.getdoc("KEY") == "Описание"
        message = FakeMessage(".legacy")
        await loader.get_command("legacy").func(message)
        assert message.edits == ["v"]

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("validator", "value", "expected"),
    [
        (validators.Boolean(), "yes", True),
        (validators.Integer(minimum=0), "5", 5),
        (validators.Float(), "1,5", 1.5),
        (validators.Choice(["a", "b"]), "b", "b"),
        (validators.MultiChoice(["a", "b"]), ["a", "a"], ["a"]),
        (validators.Series(validators.Integer()), "1, 2", [1, 2]),
        (validators.String(max_len=3), "abc", "abc"),
        (validators.Link(), "https://example.com", "https://example.com"),
        (validators.TelegramID(), "-1001234", 1234),
        (validators.Union(validators.Integer(), validators.NoneType()), "", None),
        (validators.Hidden(), "token", "token"),
        (validators.RegExp(r"^\d+$"), "123", "123"),
    ],
)
def test_validators(validator, value, expected):
    assert validator.validate(value) == expected


@pytest.mark.parametrize(
    ("validator", "value"),
    [
        (validators.Boolean(), "maybe"),
        (validators.Integer(maximum=3), "4"),
        (validators.String(length=2), "abc"),
        (validators.Link(), "not a link"),
        (validators.Choice(["a"]), "z"),
    ],
)
def test_validators_reject(validator, value):
    with pytest.raises(validators.ValidationError):
        validator.validate(value)


def test_hikkatl_is_telethon():
    from uroboros.hikka import aliases

    aliases.install()
    import telethon
    from hikkatl.tl.types import Message

    assert Message is telethon.tl.types.Message
