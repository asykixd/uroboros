# meta developer: @uroboros
# requires_uroboros: 0.2
"""Command filters and user lookup: by reply, @username or private chat."""

from uroboros import Module, command, utils


class Who(Module):
    """User info"""

    @command("who")
    async def who(self, message):
        """[@username | id] — who is this (or reply to a message)"""
        user = await utils.get_target(message)
        if user is None:
            await utils.answer(message, "❌ Reply to a message or pass @username")
            return
        name = getattr(user, "first_name", None) or getattr(user, "title", "")
        await utils.answer(
            message,
            f"👤 <b>{utils.escape_html(name)}</b>\n" + utils.quote(f"id: <code>{user.id}</code>"),
        )

    @command("pmonly", only_pm=True)
    async def pmonly(self, message):
        """— works in private chats only"""
        await utils.answer(message, "✅ This is a private chat")
