from uroboros import Module, command, utils
from uroboros.database import MAIN_OWNER


class Settings(Module):
    """Префикс и алиасы команд"""

    def _aliases(self):
        return self.db.raw.get(MAIN_OWNER, "aliases", {})

    @command("setprefix", access="owner")
    async def setprefix(self, message):
        """<префикс> — сменить префикс команд"""
        prefix = utils.get_args_raw(message).strip()
        if not prefix or len(prefix) > 3 or any(ch.isspace() for ch in prefix):
            await utils.answer(message, "❌ Префикс — от 1 до 3 символов без пробелов")
            return
        self.db.raw.set(MAIN_OWNER, "prefix", prefix)
        await utils.answer(message, f"✅ Префикс: <code>{utils.escape_html(prefix)}</code>")

    @command("alias", access="owner")
    async def alias(self, message):
        """<алиас> <команда> — добавить алиас"""
        args = utils.get_args(message)
        if len(args) != 2:
            await utils.answer(message, "❌ Использование: <code>alias алиас команда</code>")
            return
        alias, target = args[0].lower(), args[1].lower()
        cmd = self.loader.get_command(target)
        if cmd is None:
            await utils.answer(message, f"❌ Команды <code>{utils.escape_html(target)}</code> нет")
            return
        if self.loader.get_command(alias) is not None:
            await utils.answer(message, f"❌ <code>{utils.escape_html(alias)}</code> уже является командой")
            return
        aliases = self._aliases()
        aliases[alias] = cmd.name
        self.db.raw.set(MAIN_OWNER, "aliases", aliases)
        await utils.answer(message, f"✅ Алиас <code>{utils.escape_html(alias)}</code> → <code>{cmd.name}</code>")

    @command("unalias", access="owner")
    async def unalias(self, message):
        """<алиас> — удалить алиас"""
        alias = utils.get_args_raw(message).strip().lower()
        aliases = self._aliases()
        if alias not in aliases:
            await utils.answer(message, "❌ Такого алиаса нет")
            return
        del aliases[alias]
        self.db.raw.set(MAIN_OWNER, "aliases", aliases)
        await utils.answer(message, f"🗑 Алиас <code>{utils.escape_html(alias)}</code> удалён")

    @command("aliases")
    async def aliases(self, message):
        """— список алиасов"""
        aliases = self._aliases()
        if not aliases:
            await utils.answer(message, "🔗 Алиасов нет")
            return
        lines = [
            f"<code>{utils.escape_html(a)}</code> → <code>{utils.escape_html(c)}</code>"
            for a, c in sorted(aliases.items())
        ]
        await utils.answer(message, "🔗 <b>Алиасы</b>\n" + utils.quote("\n".join(lines)))
