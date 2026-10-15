from uroboros import Module, command, utils
from uroboros.database import MAIN_OWNER

EDIT_COMMANDS_KEY = "edit_commands"
LANGUAGE_NAMES = {"ru": "🇷🇺 Русский", "en": "🇬🇧 English"}


class Settings(Module):
    """Prefix, aliases, re-running edited commands and the bot language"""

    strings = {
        "bad_prefix": "❌ <b>Not suitable</b>",
        "bad_prefix_hint": "a prefix is 1 to 3 characters without spaces",
        "prefix": "⌨️ <b>Prefix</b> <code>{prefix}</code>",
        "prefix_hint": "commands now look like this: <code>{prefix}help</code>",
        "alias_usage": "❌ <b>Which alias to add?</b>",
        "alias_usage_hint": "<code>alias alias command</code>",
        "no_command": "❌ <b>No command</b> <code>{name}</code>",
        "already_command": "❌ <code>{name}</code> <b>is already a command</b>",
        "alias_added": "🏷 <b>Alias added</b> · <code>{alias}</code> → <code>{command}</code>",
        "no_alias": "❌ <b>No such alias</b>",
        "alias_removed": "🗑 <b>Alias</b> <code>{alias}</code> <b>removed</b>",
        "no_aliases": "🏷 <b>No aliases</b>",
        "no_aliases_hint": "add one: <code>alias alias command</code>",
        "aliases": "🏷 <b>Aliases</b> · {count}",
        "language": "🌐 <b>Language</b> · {name}",
        "language_hint": "change: {options}",
        "unknown_language": "❌ <b>No such language</b>",
        "unknown": "❌ <b>Didn't understand</b>",
        "editcmd_usage": "<code>editcmd on</code> or <code>editcmd off</code>",
        "editcmd_on": "✏️ <b>Re-running edited commands is on</b>",
        "editcmd_on_note": "🔁 Fix a command in its message and it runs again",
        "editcmd_off_hint": "turn off: <code>{prefix}editcmd off</code>",
        "editcmd_off": "✏️ <b>Re-running edited commands is off</b>",
        "editcmd_on_hint": "turn on: <code>{prefix}editcmd on</code>",
    }
    strings_ru = {
        "_cls_doc": "Префикс, алиасы, запуск команд по правке и язык бота",
        "_cmd_doc_editcmd": "[on | off] — перезапускать команду, если её сообщение отредактировали",
        "_cmd_doc_setprefix": "<префикс> — сменить префикс команд",
        "_cmd_doc_alias": "<алиас> <команда> — добавить алиас",
        "_cmd_doc_unalias": "<алиас> — удалить алиас",
        "_cmd_doc_aliases": "— список алиасов",
        "_cmd_doc_lang": "[ru | en] — язык интерфейса бота",
        "bad_prefix": "❌ <b>Не подходит</b>",
        "bad_prefix_hint": "префикс — от 1 до 3 символов без пробелов",
        "prefix": "⌨️ <b>Префикс</b> <code>{prefix}</code>",
        "prefix_hint": "теперь команды так: <code>{prefix}help</code>",
        "alias_usage": "❌ <b>Какой алиас добавить?</b>",
        "alias_usage_hint": "<code>alias алиас команда</code>",
        "no_command": "❌ <b>Нет команды</b> <code>{name}</code>",
        "already_command": "❌ <code>{name}</code> <b>уже команда</b>",
        "alias_added": "🏷 <b>Алиас добавлен</b> · <code>{alias}</code> → <code>{command}</code>",
        "no_alias": "❌ <b>Такого алиаса нет</b>",
        "alias_removed": "🗑 <b>Алиас</b> <code>{alias}</code> <b>удалён</b>",
        "no_aliases": "🏷 <b>Алиасов нет</b>",
        "no_aliases_hint": "добавить: <code>alias алиас команда</code>",
        "aliases": "🏷 <b>Алиасы</b> · {count}",
        "language": "🌐 <b>Язык</b> · {name}",
        "language_hint": "сменить: {options}",
        "unknown_language": "❌ <b>Нет такого языка</b>",
        "unknown": "❌ <b>Не понял</b>",
        "editcmd_usage": "<code>editcmd on</code> или <code>editcmd off</code>",
        "editcmd_on": "✏️ <b>Команды по правке включены</b>",
        "editcmd_on_note": "🔁 Исправили команду в сообщении — она выполнится заново",
        "editcmd_off_hint": "выключить: <code>{prefix}editcmd off</code>",
        "editcmd_off": "✏️ <b>Команды по правке выключены</b>",
        "editcmd_on_hint": "включить: <code>{prefix}editcmd on</code>",
    }

    def _aliases(self):
        return self.db.raw.get(MAIN_OWNER, "aliases", {})

    @command("setprefix", access="owner", emoji="⌨️")
    async def setprefix(self, message):
        """<prefix> — change the command prefix"""
        prefix = utils.get_args_raw(message).strip()
        if not prefix or len(prefix) > 3 or any(ch.isspace() for ch in prefix):
            await utils.answer(message, utils.card(self.strings("bad_prefix"), hint=self.strings("bad_prefix_hint")))
            return
        self.db.raw.set(MAIN_OWNER, "prefix", prefix)
        await utils.answer(
            message,
            utils.card(self.strings("prefix", prefix=prefix), hint=self.strings("prefix_hint", prefix=prefix)),
        )

    @command("alias", access="owner", emoji="🏷")
    async def alias(self, message):
        """<alias> <command> — add an alias"""
        args = utils.get_args(message)
        if len(args) != 2:
            await utils.answer(message, utils.card(self.strings("alias_usage"), hint=self.strings("alias_usage_hint")))
            return
        alias, target = args[0].lower(), args[1].lower()
        cmd = self.loader.get_command(target)
        if cmd is None:
            await utils.answer(message, self.strings("no_command", name=target))
            return
        if self.loader.get_command(alias) is not None:
            await utils.answer(message, self.strings("already_command", name=alias))
            return
        aliases = self._aliases()
        aliases[alias] = cmd.name
        self.db.raw.set(MAIN_OWNER, "aliases", aliases)
        await utils.answer(message, self.strings("alias_added", alias=alias, command=cmd.name))

    @command("unalias", access="owner", emoji="🗑")
    async def unalias(self, message):
        """<alias> — remove an alias"""
        alias = utils.get_args_raw(message).strip().lower()
        aliases = self._aliases()
        if alias not in aliases:
            await utils.answer(message, self.strings("no_alias"))
            return
        del aliases[alias]
        self.db.raw.set(MAIN_OWNER, "aliases", aliases)
        await utils.answer(message, self.strings("alias_removed", alias=alias))

    @command("aliases", emoji="🏷")
    async def aliases(self, message):
        """— list aliases"""
        aliases = self._aliases()
        if not aliases:
            await utils.answer(message, utils.card(self.strings("no_aliases"), hint=self.strings("no_aliases_hint")))
            return
        lines = [
            f"▸ <code>{utils.escape_html(a)}</code> → <code>{utils.escape_html(c)}</code>"
            for a, c in sorted(aliases.items())
        ]
        await utils.answer(message, utils.card(self.strings("aliases", count=len(aliases)), lines))

    @command("lang", access="owner", emoji="🌐")
    async def lang(self, message):
        """[ru | en] — bot interface language"""
        code = utils.get_args_raw(message).strip().lower()
        if code and code not in utils.LANGUAGES:
            await utils.answer(message, self._language_card(self.strings("unknown_language")))
            return
        if code:
            self.db.raw.set(MAIN_OWNER, "lang", code)
            self.loader.apply_language()
        current = utils.get_language(self.db.raw)
        await utils.answer(message, self._language_card(self.strings("language", name=LANGUAGE_NAMES[current])))

    def _language_card(self, title):
        prefix = utils.escape_html(utils.get_prefix(self.db.raw))
        options = ", ".join(f"<code>{prefix}lang {code}</code>" for code in utils.LANGUAGES)
        return utils.card(title, hint=self.strings("language_hint", options=utils.Html(options)))

    @command("editcmd", access="owner", emoji="✏️")
    async def editcmd(self, message):
        """[on | off] — re-run a command when its message is edited"""
        arg = utils.get_args_raw(message).strip().lower()
        if arg not in ("", "on", "off"):
            await utils.answer(message, utils.card(self.strings("unknown"), hint=self.strings("editcmd_usage")))
            return
        if arg:
            self.db.raw.set(MAIN_OWNER, EDIT_COMMANDS_KEY, arg == "on")
        prefix = utils.get_prefix(self.db.raw)
        if self.db.raw.get(MAIN_OWNER, EDIT_COMMANDS_KEY, True):
            card = utils.card(
                self.strings("editcmd_on"),
                [self.strings("editcmd_on_note")],
                hint=self.strings("editcmd_off_hint", prefix=prefix),
            )
        else:
            card = utils.card(self.strings("editcmd_off"), hint=self.strings("editcmd_on_hint", prefix=prefix))
        await utils.answer(message, card)
