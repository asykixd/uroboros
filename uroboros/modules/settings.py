from uroboros import Module, command, utils
from uroboros.database import MAIN_OWNER


class Settings(Module):
    """Префикс и алиасы команд"""

    def _aliases(self):
        return self.db.raw.get(MAIN_OWNER, "aliases", {})

    @command("setprefix", access="owner", emoji="⌨️")
    async def setprefix(self, message):
        """<префикс> — сменить префикс команд"""
        prefix = utils.get_args_raw(message).strip()
        if not prefix or len(prefix) > 3 or any(ch.isspace() for ch in prefix):
            await utils.answer(
                message, utils.card("❌ <b>Не подходит</b>", hint="префикс — от 1 до 3 символов без пробелов")
            )
            return
        self.db.raw.set(MAIN_OWNER, "prefix", prefix)
        escaped = utils.escape_html(prefix)
        await utils.answer(
            message,
            utils.card(
                f"⌨️ <b>Префикс</b> <code>{escaped}</code>", hint=f"теперь команды так: <code>{escaped}help</code>"
            ),
        )

    @command("alias", access="owner", emoji="🏷")
    async def alias(self, message):
        """<алиас> <команда> — добавить алиас"""
        args = utils.get_args(message)
        if len(args) != 2:
            await utils.answer(
                message, utils.card("❌ <b>Какой алиас добавить?</b>", hint="<code>alias алиас команда</code>")
            )
            return
        alias, target = args[0].lower(), args[1].lower()
        cmd = self.loader.get_command(target)
        if cmd is None:
            await utils.answer(message, f"❌ <b>Нет команды</b> <code>{utils.escape_html(target)}</code>")
            return
        if self.loader.get_command(alias) is not None:
            await utils.answer(message, f"❌ <code>{utils.escape_html(alias)}</code> <b>уже команда</b>")
            return
        aliases = self._aliases()
        aliases[alias] = cmd.name
        self.db.raw.set(MAIN_OWNER, "aliases", aliases)
        await utils.answer(
            message, f"🏷 <b>Алиас добавлен</b> · <code>{utils.escape_html(alias)}</code> → <code>{cmd.name}</code>"
        )

    @command("unalias", access="owner", emoji="🗑")
    async def unalias(self, message):
        """<алиас> — удалить алиас"""
        alias = utils.get_args_raw(message).strip().lower()
        aliases = self._aliases()
        if alias not in aliases:
            await utils.answer(message, "❌ <b>Такого алиаса нет</b>")
            return
        del aliases[alias]
        self.db.raw.set(MAIN_OWNER, "aliases", aliases)
        await utils.answer(message, f"🗑 <b>Алиас</b> <code>{utils.escape_html(alias)}</code> <b>удалён</b>")

    @command("aliases", emoji="🏷")
    async def aliases(self, message):
        """— список алиасов"""
        aliases = self._aliases()
        if not aliases:
            await utils.answer(
                message, utils.card("🏷 <b>Алиасов нет</b>", hint="добавить: <code>alias алиас команда</code>")
            )
            return
        lines = [
            f"▸ <code>{utils.escape_html(a)}</code> → <code>{utils.escape_html(c)}</code>"
            for a, c in sorted(aliases.items())
        ]
        await utils.answer(message, utils.card(f"🏷 <b>Алиасы</b> · {len(aliases)}", lines))
