# requires_uroboros: 0.2
"""Библиотека: общий код для нескольких модулей. Подключается через self.import_lib(url)."""

from uroboros import Library


class TextLib(Library):
    async def on_load(self):
        self.calls = 0

    def shout(self, text: str) -> str:
        self.calls += 1
        return text.upper() + "!"
