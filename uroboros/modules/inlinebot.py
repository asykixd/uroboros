from uroboros import Module, command, utils
from uroboros.inline.manager import TOKEN_ENV


class InlineBot(Module):
    """Inline-бот: кнопки и формы"""

    @command("inlinebot")
    async def inlinebot(self, message):
        """[токен | new | on | off] — состояние inline-бота, свой токен, новый бот, включить или выключить"""
        manager = self.loader.inline
        if manager is None:
            await utils.answer(message, "❌ Inline-бот недоступен")
            return
        arg = utils.get_args_raw(message).strip()

        if arg == "off":
            await manager.disable()
            await utils.answer(message, "✅ Inline-бот выключен. Включить: <code>inlinebot on</code>")
            return
        if arg in ("on", "new") or (arg and ":" in arg):
            await utils.answer(message, "⏳ Настраиваю inline-бота...")
            if arg == "on":
                await manager.enable()
            elif arg == "new":
                await manager.create_bot()
            else:
                await manager.set_token(arg)
        elif arg:
            await utils.answer(message, "❌ Нужен токен бота, <code>new</code>, <code>on</code> или <code>off</code>")
            return

        await utils.answer(message, self._status(manager))

    @staticmethod
    def _status(manager):
        if not manager.ready:
            reason = utils.escape_html(manager.error or "причина в логах (.logs)")
            return f"❌ <b>Inline-бот не запущен</b>\n{utils.quote(reason)}"
        lines = [f"<b>Бот:</b> @{utils.escape_html(manager.bot_username)}"]
        if manager.token_from_env:
            lines.append(f"<b>Токен:</b> из переменной <code>{TOKEN_ENV}</code>")
        return "✅ <b>Inline-бот работает</b>\n" + utils.quote("\n".join(lines))
