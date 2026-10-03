# meta developer: @uroboros
"""Inline-форма: кнопки, ввод текста, подтверждение и inline-команда."""

from uroboros import Module, command, inline_handler


class Counter(Module):
    """Счётчик с кнопками"""

    @command("counter")
    async def counter(self, message):
        """— счётчик с кнопками"""
        await self.inline.form(message, self._text(0), self._buttons(0))

    @staticmethod
    def _text(value):
        return f"🔢 <b>Счёт:</b> <code>{value}</code>"

    def _buttons(self, value):
        return [
            [
                {"text": "−", "callback": self._add, "args": (value, -1)},
                {"text": "+", "callback": self._add, "args": (value, 1)},
            ],
            [{"text": "✍️ Задать", "input": "Новое значение", "handler": self._typed}],
            [
                {"text": "Сбросить", "callback": self._add, "args": (0, 0), "confirm": "Сбросить счёт?"},
                {"text": "✖ Закрыть", "action": "close"},
            ],
        ]

    async def _add(self, call, value, delta):
        value += delta
        await call.edit(self._text(value), self._buttons(value))

    async def _typed(self, call, text):
        if not text.lstrip("-").isdigit():
            await call.edit("❌ Нужно целое число", self._buttons(0))
            return
        await call.edit(self._text(int(text)), self._buttons(int(text)))

    @inline_handler()
    async def count_inline_handler(self, query):
        """<число> — отправить счётчик в любой чат"""
        value = int(query.args) if query.args.lstrip("-").isdigit() else 0
        return {
            "title": f"Счётчик с {value}",
            "message": self._text(value),
            "buttons": self._buttons(value),
        }
