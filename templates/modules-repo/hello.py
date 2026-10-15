# meta developer: @your_username
# meta version: 1.0
# meta permissions: none
# requires_uroboros: 1.0
"""Example module: a command with a setting, strings and a card reply. Replace it with your own."""

from uroboros import ConfigValue, Module, ModuleConfig, command, utils, validators


class Hello(Module):
    """Says hello"""

    strings = {
        "hello": "👋 <b>Hello, {name}!</b>",
    }

    def __init__(self):
        self.config = ModuleConfig(
            ConfigValue("name", "world", "Default name to greet", validators.String(max_len=64)),
        )

    @command("hello", emoji="👋")
    async def hello(self, message):
        """[name] — say hello"""
        name = utils.get_args_raw(message) or self.config["name"]
        await utils.answer(
            message,
            utils.card(
                self.strings("hello", name=name),
                hint="change the default name: <code>.cfg hello name</code>",
            ),
        )
