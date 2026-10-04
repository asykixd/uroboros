# meta developer: @uroboros
# requires_uroboros: 0.3
"""Inline form: buttons, text input, confirmation and an inline command."""

from uroboros import Module, command, inline_handler


class Counter(Module):
    """Counter with buttons"""

    @command("counter")
    async def counter(self, message):
        """— counter with buttons"""
        await self.inline.form(message, self._text(0), self._buttons(0))

    @staticmethod
    def _text(value):
        return f"🔢 <b>Count:</b> <code>{value}</code>"

    def _buttons(self, value):
        return [
            [
                {"text": "−", "callback": self._add, "args": (value, -1)},
                {"text": "+", "callback": self._add, "args": (value, 1)},
            ],
            [{"text": "✍️ Set", "input": "New value", "handler": self._typed}],
            [
                {"text": "Reset", "callback": self._add, "args": (0, 0), "confirm": "Reset the counter?"},
                {"text": "✖ Close", "action": "close"},
            ],
        ]

    async def _add(self, call, value, delta):
        value += delta
        await call.edit(self._text(value), self._buttons(value))

    async def _typed(self, call, text):
        if not text.lstrip("-").isdigit():
            await call.edit("❌ Integer required", self._buttons(0))
            return
        await call.edit(self._text(int(text)), self._buttons(int(text)))

    @inline_handler()
    async def count_inline_handler(self, query):
        """<number> — send a counter to any chat"""
        value = int(query.args) if query.args.lstrip("-").isdigit() else 0
        return {
            "title": f"Counter from {value}",
            "message": self._text(value),
            "buttons": self._buttons(value),
        }
