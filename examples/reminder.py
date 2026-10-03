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
