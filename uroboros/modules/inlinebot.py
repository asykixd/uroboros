from uroboros import Module, command, utils
from uroboros.inline.manager import TOKEN_ENV


class InlineBot(Module):
    """Inline-бот: кнопки и формы"""

    @command("inlinebot", access="owner", emoji="🤖")
    async def inlinebot(self, message):
        """[токен | new | on | off] — состояние inline-бота, свой токен, новый бот, включить или выключить"""
        manager = self.loader.inline
        if manager is None:
            await utils.answer(message, "❌ <b>Inline-бот недоступен</b>")
            return
        arg = utils.get_args_raw(message).strip()

        if arg == "off":
            await manager.disable()
            await utils.answer(
                message, utils.card("🤖 <b>Inline-бот выключен</b>", hint="включить: <code>inlinebot on</code>")
            )
            return
        if arg in ("on", "new") or (arg and ":" in arg):
            await utils.answer(message, "⏳ <b>Настраиваю inline-бота...</b>")
            if arg == "on":
                await manager.enable()
            elif arg == "new":
                await manager.create_bot()
            else:
                await manager.set_token(arg)
        elif arg:
            await utils.answer(
                message,
                utils.card(
                    "❌ <b>Не понял</b>",
                    [
                        "🔑 <code>inlinebot токен</code> — свой бот",
                        "🆕 <code>inlinebot new</code> — создать нового",
                        "🟢 <code>inlinebot on</code> · 🔴 <code>inlinebot off</code>",
                    ],
                ),
            )
            return

        await utils.answer(message, self._status(manager))

    @staticmethod
    def _status(manager):
        if not manager.ready:
            reason = utils.escape_html(manager.error or "причина в логах (.logs)")
            return utils.card(
                "❌ <b>Inline-бот не запущен</b>", reason, hint="создать нового: <code>inlinebot new</code>"
            )
        lines = [f"🤖 Бот: @{utils.escape_html(manager.bot_username)}"]
        if manager.token_from_env:
            lines.append(f"🔑 Токен: из переменной <code>{TOKEN_ENV}</code>")
        return utils.card("✅ <b>Inline-бот работает</b>", lines, hint="формы с кнопками и inline-команды доступны")
