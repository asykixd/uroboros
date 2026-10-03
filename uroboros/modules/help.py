from uroboros import Module, command, utils


class Help(Module):
    """Справка по модулям и командам"""

    @command("help", aliases=["modules"])
    async def help(self, message):
        """[модуль или команда] — список модулей или справка по одному"""
        query = utils.get_args_raw(message).strip()
        prefix = utils.get_prefix(self.db.raw)
        if query:
            await self._module_help(message, query.removeprefix(prefix), prefix)
        else:
            await self._overview(message, prefix)

    def _line(self, module):
        names = ", ".join(cmd.name for cmd in self.loader.module_commands(module))
        return f"<b>{utils.escape_html(module.name)}</b> — {names or 'нет команд'}"

    async def _overview(self, message, prefix):
        modules = sorted(self.loader.modules.values(), key=lambda m: m.name.lower())
        builtin = [m for m in modules if m.is_builtin]
        external = [m for m in modules if not m.is_builtin]

        text = f"📦 <b>Модули</b> · {len(modules)}\n"
        text += utils.quote("\n".join(self._line(m) for m in builtin))
        if external:
            text += "\n<b>Установленные</b>\n"
            text += utils.quote("\n".join(self._line(m) for m in external), expandable=len(external) > 10)
        text += f"\n<i>Подробнее:</i> <code>{prefix}help модуль</code>"
        await utils.answer(message, text)

    async def _module_help(self, message, query, prefix):
        module = self.loader.get_module(query)
        if module is None:
            cmd = self.loader.get_command(query)
            module = cmd.module if cmd else None
        if module is None:
            await utils.answer(message, f"❌ Нет модуля или команды <code>{utils.escape_html(query)}</code>")
            return

        text = f"📦 <b>{utils.escape_html(module.name)}</b>\n"
        if type(module).__doc__:
            text += f"<i>{utils.escape_html(type(module).__doc__.strip())}</i>\n"

        lines = []
        for cmd in self.loader.module_commands(module):
            aliases = f" <i>({', '.join(cmd.info.aliases)})</i>" if cmd.info.aliases else ""
            doc = f" {utils.escape_html(cmd.info.doc)}" if cmd.info.doc else ""
            restrictions = cmd.info.restrictions()
            limits = f" <i>[{utils.escape_html(', '.join(restrictions))}]</i>" if restrictions else ""
            lines.append(f"<code>{prefix}{cmd.name}</code>{aliases}{doc}{limits}")
        text += utils.quote("\n".join(lines) or "Нет команд")

        if not module.is_builtin:
            text += f"\n<b>Источник:</b> <code>{utils.escape_html(module._origin)}</code>"
        await utils.answer(message, text)
