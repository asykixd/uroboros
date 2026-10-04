# meta developer: @uroboros
# meta version: 1.0
# meta permissions: none
# requires_uroboros: 1.0
"""Минимальный модуль: команда, настройка, строки и ответ-карточка."""

from uroboros import ConfigValue, Module, ModuleConfig, command, utils, validators


class Hello(Module):
    """Здоровается"""

    strings = {
        "hello": "👋 <b>Привет, {name}!</b>",
        "count": "🔁 Здоровались уже <code>{n}</code> раз",
    }

    def __init__(self):
        self.config = ModuleConfig(
            ConfigValue("name", "мир", "С кем здороваться по умолчанию", validators.String(max_len=64)),
        )

    @command("hello", aliases=["hi"], emoji="👋")
    async def hello(self, message):
        """[имя] — поздороваться"""
        name = utils.get_args_raw(message) or self.config["name"]
        self.set("count", self.get("count", 0) + 1)
        await utils.answer(
            message,
            utils.card(
                self.strings("hello", name=name),
                self.strings("count", n=self.get("count")),
                hint="поменять имя по умолчанию: <code>.cfg hello name</code>",
            ),
        )
