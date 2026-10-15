from uroboros import Module, command, utils
from uroboros.errors import InlineError
from uroboros.security import DEFAULT_LEVEL

PAGE_SIZE = 12
ROW_SIZE = 3


class Help(Module):
    """Help on modules and commands"""

    strings = {
        "no_commands": "<i>no commands</i>",
        "no_commands_cap": "<i>No commands</i>",
        "modules": "📦 <b>Modules</b> · {count}",
        "builtin": "🧩 <b>Built-in</b>",
        "installed": "📥 <b>Installed</b> · {count}",
        "more": "💡 <i>More: <code>{prefix}help module</code></i>",
        "pick": "pick a module with a button",
        "close": "✖️ Close",
        "back": "◀️ Back",
        "unloaded": "The module is already unloaded",
        "not_found": "❌ <b>No module or command</b> <code>{query}</code>",
        "not_found_hint": "module list: <code>{prefix}help</code>",
        "access": "access: {level}",
        "bot": "bot",
        "version": "🏷 Version: <code>{version}</code>",
        "developer": "👤 Author: {developer}",
        "permissions": "🔐 Permissions: {permissions}",
        "source": "🔗 Source: <code>{origin}</code>",
        "level_owner": "owners",
        "level_sudo": "sudo",
        "level_support": "support",
        "level_everyone": "everyone",
    }
    strings_ru = {
        "_cls_doc": "Справка по модулям и командам",
        "_cmd_doc_help": "[модуль или команда] — список модулей или справка по одному",
        "no_commands": "<i>нет команд</i>",
        "no_commands_cap": "<i>Нет команд</i>",
        "modules": "📦 <b>Модули</b> · {count}",
        "builtin": "🧩 <b>Встроенные</b>",
        "installed": "📥 <b>Установленные</b> · {count}",
        "more": "💡 <i>Подробнее: <code>{prefix}help модуль</code></i>",
        "pick": "выберите модуль кнопкой",
        "close": "✖️ Закрыть",
        "back": "◀️ Назад",
        "unloaded": "Модуль уже выгружен",
        "not_found": "❌ <b>Нет модуля или команды</b> <code>{query}</code>",
        "not_found_hint": "список модулей: <code>{prefix}help</code>",
        "access": "доступ: {level}",
        "bot": "бот",
        "version": "🏷 Версия: <code>{version}</code>",
        "developer": "👤 Автор: {developer}",
        "permissions": "🔐 Права: {permissions}",
        "source": "🔗 Источник: <code>{origin}</code>",
        "level_owner": "владельцы",
        "level_sudo": "sudo",
        "level_support": "support",
        "level_everyone": "все",
    }

    @command("help", aliases=["modules"], access="support", emoji="📖")
    async def help(self, message):
        """[module or command] — list modules or help on one"""
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
                pass  # e.g. inline bots are banned in this chat: answer with text
        await self._overview(message, prefix)

    def _prefix(self):
        return utils.get_prefix(self.db.raw)

    def _line(self, module):
        names = ", ".join(cmd.name for cmd in self.loader.module_commands(module))
        return f"▸ <b>{utils.escape_html(module.name)}</b> — {names or self.strings('no_commands')}"

    def _sorted(self):
        modules = sorted(self.loader.modules.values(), key=lambda m: m.name.lower())
        return [m for m in modules if m.is_builtin] + [m for m in modules if not m.is_builtin]

    async def _overview(self, message, prefix):
        modules = self._sorted()
        builtin = [m for m in modules if m.is_builtin]
        external = [m for m in modules if not m.is_builtin]

        text = self.strings("modules", count=len(modules)) + "\n" + self.strings("builtin") + "\n"
        text += utils.quote("\n".join(self._line(m) for m in builtin))
        if external:
            text += "\n" + self.strings("installed", count=len(external)) + "\n"
            text += utils.quote("\n".join(self._line(m) for m in external), expandable=len(external) > 10)
        text += "\n" + self.strings("more", prefix=prefix)
        await utils.answer(message, text)

    # --- inline: module pages with buttons ---

    def _page(self, page):
        modules = self._sorted()
        pages = max(1, -(-len(modules) // PAGE_SIZE))
        page %= pages
        chunk = modules[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

        text = utils.card(
            self.strings("modules", count=len(modules)),
            [self._line(m) for m in chunk],
            hint=self.strings("pick"),
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
        buttons.append([{"text": self.strings("close"), "action": "close"}])
        return text, buttons

    async def _turn(self, call, page):
        await call.edit(*self._page(page))

    async def _open(self, call, name, page):
        module = self.loader.get_module(name)
        if module is None:
            await call.answer(self.strings("unloaded"), show_alert=True)
            await call.edit(*self._page(page))
            return
        await call.edit(
            self._module_text(module, self._prefix()),
            [
                [
                    {"text": self.strings("back"), "callback": self._turn, "args": (page,)},
                    {"text": self.strings("close"), "action": "close"},
                ]
            ],
        )

    # --- help on one module ---

    async def _module_help(self, message, query, prefix):
        module = self.loader.get_module(query)
        if module is None:
            cmd = self.loader.get_command(query)
            module = cmd.module if cmd else None
        if module is None:
            await utils.answer(
                message,
                utils.card(self.strings("not_found", query=query), hint=self.strings("not_found_hint", prefix=prefix)),
            )
            return
        await utils.answer(message, self._module_text(module, prefix))

    def _module_text(self, module, prefix):
        text = f"🧩 <b>{utils.escape_html(module.name)}</b>"
        about_module = self.loader.module_doc(module)
        if about_module:
            text += f" · <i>{utils.escape_html(about_module)}</i>"
        text += "\n"

        lines = []
        for cmd in self.loader.module_commands(module):
            aliases = f" <i>({', '.join(cmd.info.aliases)})</i>" if cmd.info.aliases else ""
            about = self.loader.command_doc(cmd)
            doc = f" {utils.escape_html(about)}" if about else ""
            restrictions = cmd.info.restrictions()
            level = self.loader.security.required(cmd)
            if level != DEFAULT_LEVEL:
                restrictions.append(self.strings("access", level=self.strings(f"level_{level}")))
            limits = f" <i>[{utils.escape_html(', '.join(restrictions))}]</i>" if restrictions else ""
            icon = cmd.info.emoji or "▸"
            lines.append(f"{icon} <code>{utils.escape_html(prefix)}{cmd.name}</code>{aliases}{doc}{limits}")
        bot = self.inline.bot_username
        for name, handler in sorted(self.loader.inline_handlers.items()):
            if handler.module is module:
                doc = f" {utils.escape_html(handler.info.doc)}" if handler.info.doc else ""
                bot_name = utils.escape_html(bot or self.strings("bot"))
                lines.append(f"🤖 <code>@{bot_name} {utils.escape_html(name)}</code>{doc}")
        text += utils.quote("\n".join(lines) or self.strings("no_commands_cap"))

        if not module.is_builtin:
            meta = module._meta
            about = []
            if meta.get("version"):
                about.append(self.strings("version", version=meta["version"]))
            if meta.get("developer"):
                about.append(self.strings("developer", developer=meta["developer"]))
            if meta.get("permissions"):
                about.append(self.strings("permissions", permissions=meta["permissions"]))
            about.append(self.strings("source", origin=module._origin))
            text += utils.quote("\n".join(about))
        return text
