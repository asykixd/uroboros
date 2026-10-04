from uroboros import Module, command, utils
from uroboros.errors import InlineError
from uroboros.security import DEFAULT_LEVEL, LEVEL_NAMES

PAGE_SIZE = 12
ROW_SIZE = 3


class Help(Module):
    """Справка по модулям и командам"""

    @command("help", aliases=["modules"], access="support", emoji="📖")
    async def help(self, message):
        """[модуль или команда] — список модулей или справка по одному"""
        query = utils.get_args_raw(message).strip()
        prefix = self._prefix()
        if query:
            await self._module_help(message, query.removeprefix(prefix), prefix)
            return
        if self.inline.available:
            try:
                await self.inline.form(message, *self._page(0))
                return
            except InlineError:
                pass  # например, в чате запрещены inline-боты — покажем текстом
        await self._overview(message, prefix)

    def _prefix(self):
        return utils.get_prefix(self.db.raw)

    def _line(self, module):
        names = ", ".join(cmd.name for cmd in self.loader.module_commands(module))
        return f"▸ <b>{utils.escape_html(module.name)}</b> — {names or '<i>нет команд</i>'}"

    def _sorted(self):
        modules = sorted(self.loader.modules.values(), key=lambda m: m.name.lower())
        return [m for m in modules if m.is_builtin] + [m for m in modules if not m.is_builtin]

    async def _overview(self, message, prefix):
        modules = self._sorted()
        builtin = [m for m in modules if m.is_builtin]
        external = [m for m in modules if not m.is_builtin]

        text = f"📦 <b>Модули</b> · {len(modules)}\n🧩 <b>Встроенные</b>\n"
        text += utils.quote("\n".join(self._line(m) for m in builtin))
        if external:
            text += f"\n📥 <b>Установленные</b> · {len(external)}\n"
            text += utils.quote("\n".join(self._line(m) for m in external), expandable=len(external) > 10)
        text += f"\n💡 <i>Подробнее: <code>{utils.escape_html(prefix)}help модуль</code></i>"
        await utils.answer(message, text)

    # --- inline: страницы модулей с кнопками ---

    def _page(self, page):
        modules = self._sorted()
        pages = max(1, -(-len(modules) // PAGE_SIZE))
        page %= pages
        chunk = modules[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

        text = utils.card(
            f"📦 <b>Модули</b> · {len(modules)}",
            [self._line(m) for m in chunk],
            hint="выберите модуль кнопкой",
        )
        names = [{"text": m.name, "callback": self._open, "args": (m.name, page)} for m in chunk]
        buttons = [names[i : i + ROW_SIZE] for i in range(0, len(names), ROW_SIZE)]
        if pages > 1:
            buttons.append(
                [
                    {"text": "◀️", "callback": self._turn, "args": ((page - 1) % pages,)},
                    {"text": f"📄 {page + 1}/{pages}", "callback": self._turn, "args": (page,)},
                    {"text": "▶️", "callback": self._turn, "args": ((page + 1) % pages,)},
                ]
            )
        buttons.append([{"text": "✖️ Закрыть", "action": "close"}])
        return text, buttons

    async def _turn(self, call, page):
        await call.edit(*self._page(page))

    async def _open(self, call, name, page):
        module = self.loader.get_module(name)
        if module is None:
            await call.answer("Модуль уже выгружен", show_alert=True)
            await call.edit(*self._page(page))
            return
        await call.edit(
            self._module_text(module, self._prefix()),
            [[{"text": "◀️ Назад", "callback": self._turn, "args": (page,)}, {"text": "✖️ Закрыть", "action": "close"}]],
        )

    # --- справка по модулю ---

    async def _module_help(self, message, query, prefix):
        module = self.loader.get_module(query)
        if module is None:
            cmd = self.loader.get_command(query)
            module = cmd.module if cmd else None
        if module is None:
            await utils.answer(
                message,
                utils.card(
                    f"❌ <b>Нет модуля или команды</b> <code>{utils.escape_html(query)}</code>",
                    hint=f"список модулей: <code>{utils.escape_html(prefix)}help</code>",
                ),
            )
            return
        await utils.answer(message, self._module_text(module, prefix))

    def _module_text(self, module, prefix):
        text = f"🧩 <b>{utils.escape_html(module.name)}</b>"
        if type(module).__doc__:
            text += f" · <i>{utils.escape_html(type(module).__doc__.strip())}</i>"
        text += "\n"

        lines = []
        for cmd in self.loader.module_commands(module):
            aliases = f" <i>({', '.join(cmd.info.aliases)})</i>" if cmd.info.aliases else ""
            doc = f" {utils.escape_html(cmd.info.doc)}" if cmd.info.doc else ""
            restrictions = cmd.info.restrictions()
            level = self.loader.security.required(cmd)
            if level != DEFAULT_LEVEL:
                restrictions.append(f"доступ: {LEVEL_NAMES[level]}")
            limits = f" <i>[{utils.escape_html(', '.join(restrictions))}]</i>" if restrictions else ""
            icon = cmd.info.emoji or "▸"
            lines.append(f"{icon} <code>{utils.escape_html(prefix)}{cmd.name}</code>{aliases}{doc}{limits}")
        bot = self.inline.bot_username
        for name, handler in sorted(self.loader.inline_handlers.items()):
            if handler.module is module:
                doc = f" {utils.escape_html(handler.info.doc)}" if handler.info.doc else ""
                lines.append(f"🤖 <code>@{utils.escape_html(bot or 'бот')} {utils.escape_html(name)}</code>{doc}")
        text += utils.quote("\n".join(lines) or "<i>Нет команд</i>")

        if not module.is_builtin:
            meta = module._meta
            about = []
            if meta.get("version"):
                about.append(f"🏷 Версия: <code>{utils.escape_html(meta['version'])}</code>")
            if meta.get("developer"):
                about.append(f"👤 Автор: {utils.escape_html(meta['developer'])}")
            if meta.get("permissions"):
                about.append(f"🔐 Права: {utils.escape_html(meta['permissions'])}")
            about.append(f"🔗 Источник: <code>{utils.escape_html(module._origin)}</code>")
            text += utils.quote("\n".join(about))
        return text
