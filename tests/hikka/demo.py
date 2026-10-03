# meta developer: @someone
# scope: hikka_min 1.5.0
__version__ = (1, 2, 0)

import asyncio

from hikkatl.tl.types import Message

from .. import loader, utils
from ..inline.types import InlineCall, InlineQuery


@loader.tds
class DemoMod(loader.Module):
    """Demo module"""

    strings = {
        "name": "Demo",
        "hello": "Hello, <b>{}</b>!",
        "_cfg_greeting": "Greeting",
    }
    strings_ru = {
        "hello": "Привет, <b>{}</b>!",
        "_cls_doc": "Демо-модуль",
        "_cmd_doc_hi": "[имя] — поздороваться",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "times",
                1,
                lambda: "Сколько раз",
                validator=loader.validators.Integer(minimum=1, maximum=3),
            ),
            loader.ConfigValue("loud", False, "Громко", validator=loader.validators.Boolean()),
            loader.ConfigValue("names", ["a"], "Имена", validator=loader.validators.Series()),
        )
        self.ready_args = None
        self.seen = []

    async def client_ready(self, client, db):
        self.ready_args = (client, db)
        self.set("ready", True)

    @loader.command(ru_doc="[имя] — поздороваться", alias="hello")
    async def hi(self, message: Message):
        """Say hi"""
        name = utils.get_args_raw(message) or "мир"
        text = self.strings("hello").format(utils.escape_html(name)) * self.config["times"]
        await utils.answer(message, text.upper() if self.config["loud"] else text)

    async def pongcmd(self, message):
        """Legacy command"""
        await utils.answer(message, "pong")

    @loader.owner
    @loader.command()
    async def secret(self, message):
        """Owner only"""
        await utils.answer(message, "secret")

    @loader.unrestricted
    @loader.command()
    async def public(self, message):
        """For everyone"""
        await utils.answer(message, "public")

    @loader.command()
    async def form(self, message):
        """Form"""
        await self.inline.form(
            "Форма",
            message=message,
            reply_markup=[
                [{"text": "Жми", "callback": self.press, "args": (5,)}],
                [{"text": "Ответ", "action": "answer", "message": "Готово", "show_alert": True}],
            ],
        )

    async def press(self, call: InlineCall, value):
        await call.edit(f"Нажато {value}")

    @loader.watcher(only_pm=True, no_commands=True)
    async def watcher(self, message):
        self.seen.append(message.raw_text)

    @loader.loop(interval=0.01, autostart=True)
    async def ticker(self):
        self.set("ticks", self.get("ticks", 0) + 1)
        if self.get("ticks") >= 2:
            raise loader.StopLoop

    @loader.inline_handler(ru_doc="<текст> — эхо")
    async def echo_inline_handler(self, query: InlineQuery):
        return {
            "title": "Эхо",
            "description": query.args,
            "message": query.args or "пусто",
            "reply_markup": {"text": "Ок", "callback": self.press, "args": (1,)},
        }

    async def hidden_helper(self):
        await asyncio.sleep(0)
