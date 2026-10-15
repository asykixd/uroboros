# meta developer: @uroboros
# meta version: 1.0
# meta permissions: none
# requires_uroboros: 1.1
"""Minimal module: a command, a setting, strings and a card reply."""

from uroboros import ConfigValue, Module, ModuleConfig, command, utils, validators


class Hello(Module):
    """Says hello"""

    strings = {
        "hello": "👋 <b>Hello, {name}!</b>",
        "count": "🔁 Greeted <code>{n}</code> times",
        "hint": "change the default name: <code>.cfg hello name</code>",
    }
    # Shown when the bot language is Russian (.lang ru); missing keys fall back to strings.
    strings_ru = {
        "_cls_doc": "Здоровается",
        "_cmd_doc_hello": "[имя] — поздороваться",
        "hello": "👋 <b>Привет, {name}!</b>",
        "count": "🔁 Поздоровались <code>{n}</code> раз",
        "hint": "имя по умолчанию: <code>.cfg hello name</code>",
    }

    def __init__(self):
        self.config = ModuleConfig(
            ConfigValue("name", "world", "Default name to greet", validators.String(max_len=64)),
        )

    @command("hello", aliases=["hi"], emoji="👋")
    async def hello(self, message):
        """[name] — say hello"""
        name = utils.get_args_raw(message) or self.config["name"]
        self.set("count", self.get("count", 0) + 1)
        await utils.answer(
            message,
            utils.card(
                self.strings("hello", name=name),
                self.strings("count", n=self.get("count")),
                hint=self.strings("hint"),
            ),
        )
