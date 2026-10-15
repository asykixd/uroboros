from uroboros import Module, command, utils
from uroboros.inline.manager import TOKEN_ENV


class InlineBot(Module):
    """Inline bot: buttons and forms"""

    strings = {
        "unavailable": "❌ <b>The inline bot is unavailable</b>",
        "disabled": "🤖 <b>Inline bot turned off</b>",
        "enable_hint": "turn on: <code>inlinebot on</code>",
        "configuring": "⏳ <b>Setting up the inline bot...</b>",
        "unknown": "❌ <b>Didn't understand</b>",
        "use_token": "🔑 <code>inlinebot token</code> — your own bot",
        "use_new": "🆕 <code>inlinebot new</code> — create a new one",
        "not_running": "❌ <b>The inline bot isn't running</b>",
        "reason_in_logs": "the reason is in the logs (.logs)",
        "new_hint": "create a new one: <code>inlinebot new</code>",
        "bot": "🤖 Bot: @{username}",
        "token_env": "🔑 Token: from the <code>{env}</code> variable",
        "running": "✅ <b>The inline bot is running</b>",
        "running_hint": "forms with buttons and inline commands are available",
    }
    strings_ru = {
        "_cls_doc": "Inline-бот: кнопки и формы",
        "_cmd_doc_inlinebot": (
            "[токен | new | on | off] — состояние inline-бота, свой токен, новый бот, включить или выключить"
        ),
        "unavailable": "❌ <b>Inline-бот недоступен</b>",
        "disabled": "🤖 <b>Inline-бот выключен</b>",
        "enable_hint": "включить: <code>inlinebot on</code>",
        "configuring": "⏳ <b>Настраиваю inline-бота...</b>",
        "unknown": "❌ <b>Не понял</b>",
        "use_token": "🔑 <code>inlinebot токен</code> — свой бот",
        "use_new": "🆕 <code>inlinebot new</code> — создать нового",
        "not_running": "❌ <b>Inline-бот не запущен</b>",
        "reason_in_logs": "причина в логах (.logs)",
        "new_hint": "создать нового: <code>inlinebot new</code>",
        "bot": "🤖 Бот: @{username}",
        "token_env": "🔑 Токен: из переменной <code>{env}</code>",
        "running": "✅ <b>Inline-бот работает</b>",
        "running_hint": "формы с кнопками и inline-команды доступны",
    }

    @command("inlinebot", access="owner", emoji="🤖")
    async def inlinebot(self, message):
        """[token | new | on | off] — inline bot state, your own token, a new bot, turn on or off"""
        manager = self.loader.inline
        if manager is None:
            await utils.answer(message, self.strings("unavailable"))
            return
        arg = utils.get_args_raw(message).strip()

        if arg == "off":
            await manager.disable()
            await utils.answer(message, utils.card(self.strings("disabled"), hint=self.strings("enable_hint")))
            return
        if arg in ("on", "new") or (arg and ":" in arg):
            await utils.answer(message, self.strings("configuring"))
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
                    self.strings("unknown"),
                    [
                        self.strings("use_token"),
                        self.strings("use_new"),
                        "🟢 <code>inlinebot on</code> · 🔴 <code>inlinebot off</code>",
                    ],
                ),
            )
            return

        await utils.answer(message, self._status(manager))

    def _status(self, manager):
        if not manager.ready:
            reason = utils.escape_html(manager.error or self.strings("reason_in_logs"))
            return utils.card(self.strings("not_running"), reason, hint=self.strings("new_hint"))
        lines = [self.strings("bot", username=manager.bot_username)]
        if manager.token_from_env:
            lines.append(self.strings("token_env", env=TOKEN_ENV))
        return utils.card(self.strings("running"), lines, hint=self.strings("running_hint"))
