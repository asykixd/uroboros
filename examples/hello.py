# meta developer: @uroboros
# meta version: 1.0
# requires_uroboros: 0.2
"""Минимальный модуль: команда, настройка и строки."""

from uroboros import ConfigValue, Module, ModuleConfig, command, utils, validators


class Hello(Module):
    """Здоровается"""

    strings = {
        "hello": "👋 Привет, <b>{name}</b>!",
        "count": "Здоровались уже <code>{n}</code> раз",
    }

    def __init__(self):
        self.config = ModuleConfig(
            ConfigValue("name", "мир", "С кем здороваться по умолчанию", validators.String(max_len=64)),
        )

    @command("hello", aliases=["hi"])
    async def hello(self, message):
        """[имя] — поздороваться"""
        name = utils.get_args_raw(message) or self.config["name"]
        self.set("count", self.get("count", 0) + 1)
        await utils.answer(
            message,
            self.strings("hello", name=name) + "\n" + utils.quote(self.strings("count", n=self.get("count"))),
        )
