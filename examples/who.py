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
