# meta developer: @uroboros
# requires_uroboros: 0.2
"""Background task: checks reminders every minute and sends them to Saved Messages."""

import time

from uroboros import Module, command, loop, utils


class Reminder(Module):
    """Reminders in Saved Messages"""

    @command("remind", no_reply=True)
    async def remind(self, message):
        """<minutes> <text> — remind in N minutes"""
        args = utils.get_args_raw(message).split(maxsplit=1)
        if len(args) != 2 or not args[0].isdigit():
            await utils.answer(message, "❌ Usage: <code>remind 10 text</code>")
            return
        reminders = self.get("reminders", [])
        reminders.append([time.time() + int(args[0]) * 60, args[1]])
        self.set("reminders", reminders)
        await utils.answer(message, f"✅ Reminder in {int(args[0])} min")

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
