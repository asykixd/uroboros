# Примеры модулей

<!-- Сгенерировано scripts/gen_docs.py из кода — не править вручную. -->

Каждый пример загружается в тестах (`tests/test_examples.py`), поэтому код ниже рабочий для текущей версии. Установить пример: ответьте на файл командой `.lm` или `.dlm asykixd/uroboros/examples/<имя>`.

## counter

```python
# meta developer: @uroboros
# requires_uroboros: 0.3
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
```

## hello

```python
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
```

## reminder

```python
# meta developer: @uroboros
# requires_uroboros: 0.2
"""Фоновая задача: раз в минуту проверяет напоминания и шлёт их в «Избранное»."""

import time

from uroboros import Module, command, loop, utils


class Reminder(Module):
    """Напоминания в «Избранное»"""

    @command("remind", no_reply=True)
    async def remind(self, message):
        """<минуты> <текст> — напомнить через N минут"""
        args = utils.get_args_raw(message).split(maxsplit=1)
        if len(args) != 2 or not args[0].isdigit():
            await utils.answer(message, "❌ Использование: <code>remind 10 текст</code>")
            return
        reminders = self.get("reminders", [])
        reminders.append([time.time() + int(args[0]) * 60, args[1]])
        self.set("reminders", reminders)
        await utils.answer(message, f"✅ Напомню через {int(args[0])} мин")

    @loop(interval=60)
    async def check(self):
        now = time.time()
        reminders = self.get("reminders", [])
        due = [text for at, text in reminders if at <= now]
        if not due:
            return
        self.set("reminders", [[at, text] for at, text in reminders if at > now])
        for text in due:
            await self.client.send_message("me", f"⏰ {utils.escape_html(text)}", parse_mode="html")
```

## shout

```python
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
```

## textlib

```python
# requires_uroboros: 0.2
"""Библиотека: общий код для нескольких модулей. Подключается через self.import_lib(url)."""

from uroboros import Library


class TextLib(Library):
    async def on_load(self):
        self.calls = 0

    def shout(self, text: str) -> str:
        self.calls += 1
        return text.upper() + "!"
```

## who

```python
# meta developer: @uroboros
# requires_uroboros: 0.2
"""Фильтры команд и поиск пользователя: ответом, по @username или в личке."""

from uroboros import Module, command, utils


class Who(Module):
    """Информация о пользователе"""

    @command("who")
    async def who(self, message):
        """[@username | id] — кто это (или ответом на сообщение)"""
        user = await utils.get_target(message)
        if user is None:
            await utils.answer(message, "❌ Ответьте на сообщение или укажите @username")
            return
        name = getattr(user, "first_name", None) or getattr(user, "title", "")
        await utils.answer(
            message,
            f"👤 <b>{utils.escape_html(name)}</b>\n" + utils.quote(f"id: <code>{user.id}</code>"),
        )

    @command("pmonly", only_pm=True)
    async def pmonly(self, message):
        """— работает только в личных сообщениях"""
        await utils.answer(message, "✅ Это личные сообщения")
```
