# requires_uroboros: 0.2
"""Модуль, который пользуется библиотекой textlib.py."""

from uroboros import Module, command, utils

TEXTLIB = "https://raw.githubusercontent.com/asykixd/uroboros/HEAD/examples/textlib.py"


class Shout(Module):
    """Кричит текстом"""

    async def on_load(self):
        self.textlib = await self.import_lib(TEXTLIB)

    @command("shout")
    async def shout(self, message):
        """<текст> — крикнуть"""
        await utils.answer(message, utils.escape_html(self.textlib.shout(utils.get_args_raw(message))))
