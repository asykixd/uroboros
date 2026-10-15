import contextlib

from uroboros import Module, command, utils
from uroboros.errors import InlineError
from uroboros.ratelimit import format_seconds
from uroboros.security import GROUPS, LEVEL_NAMES, LEVELS

USAGE = (
    "❌ <b>Не понял</b>\n"
    "<blockquote>🔐 <code>security</code> — обзор\n"
    "⌨️ <code>security команда уровень</code> — права команды\n"
    "❄️ <code>security flood ...</code> — защита от флуда\n"
    "🛡 <code>security trust|untrust модуль</code> — защита модуля</blockquote>\n"
    "💡 <i>уровни: <code>owner</code>, <code>sudo</code>, <code>support</code>, <code>everyone</code>, "
    "<code>default</code></i>"
)
GROUP_ICONS = {"owner": "👑", "sudo": "🛡", "support": "🤝"}
CLOSE = {"text": "✖️ Закрыть", "action": "close"}
ROW_SIZE = 3
TRUST_WARNING = (
    "Защита во время работы его больше не ограничивает: он может читать сессию, завершать сеансы и менять пароль."
)


class Security(Module):
    """Доступ: владельцы, sudo, support и права на команды"""

    @command("security", access="owner", emoji="🔐")
    async def security(self, message):
        """[команда уровень | flood ... | unfreeze модуль | trust/untrust модуль] — доступ, права команд и защита"""
        args = utils.get_args(message)
        if not args:
            if self.inline.available:
                try:
                    await self.inline.form(message, *await self._root_view())
                    return
                except InlineError:
                    pass  # например, в чате запрещены inline-боты — покажем текстом
            await utils.answer(message, await self._overview())
            return
        if args[0].lower() == "flood":
            await self._flood(message, args[1:])
            return
        if args[0].lower() == "unfreeze" and len(args) == 2:
            await self._unfreeze(message, args[1])
            return
        if args[0].lower() in ("trust", "untrust") and len(args) == 2:
            await self._trust(message, args[1], args[0].lower() == "trust")
            return
        if len(args) != 2:
            await utils.answer(message, USAGE)
            return

        await utils.answer(message, self._set_level(args[0], args[1]) or USAGE)

    def _set_level(self, name, level):
        """Меняет права команды; ответ для пользователя или None, если уровень непонятен."""
        name, level = name.lower().removeprefix(utils.get_prefix(self.db.raw)), level.lower()
        cmd = self.loader.get_command(name)
        if cmd is None:
            return f"❌ <b>Нет команды</b> <code>{utils.escape_html(name)}</code>"
        if level not in (*LEVELS, "default"):
            return None
        security = self.loader.security
        security.set_required(cmd.name, None if level == "default" else level)
        required = security.required(cmd)
        return f"🔐 <b>Права изменены</b> · <code>{cmd.name}</code> — {LEVEL_NAMES[required]}" + (
            " (по умолчанию)" if required == cmd.info.access and level == "default" else ""
        )

    async def _overview(self):
        security = self.loader.security
        lines = []
        for group in GROUPS:
            members = security.members(group)
            names = ", ".join([await self._user(uid) for uid in members]) or "—"
            if group == "owner":
                names = "этот аккаунт" + (f", {names}" if members else "")
            lines.append(f"{GROUP_ICONS[group]} <b>{group}:</b> {names}")
        text = utils.card("🔐 <b>Доступ и защита</b>", lines)

        overrides = security.overrides()
        if overrides:
            items = [
                f"▸ <code>{utils.escape_html(n)}</code> — {LEVEL_NAMES.get(lv, lv)}"
                for n, lv in sorted(overrides.items())
            ]
            text += "\n⌨️ <b>Изменённые права</b>\n" + utils.quote("\n".join(items), expandable=len(items) > 10)
        limiter = self.loader.ratelimit
        settings = limiter.settings
        flood = (
            f"не больше {settings['limit']} запросов модуля за {settings['window']} с, "
            f"иначе заморозка на {settings['freeze']} с"
            if settings["enabled"]
            else "выключена"
        )
        text += f"\n❄️ <b>Защита от флуда:</b> {flood}"
        trusted = sorted(self.loader.guard.trusted())
        if trusted:
            names = {m._stem: m.name for m in self.loader.modules.values()}
            items = [f"<b>{utils.escape_html(names.get(stem, stem))}</b>" for stem in trusted]
            text += "\n🛡 <b>Без защиты во время работы</b>\n" + utils.quote(", ".join(items))
        frozen = [(name, limiter.frozen_for(name)) for name in list(limiter.frozen)]
        frozen = [f"<b>{utils.escape_html(n)}</b> — ещё {format_seconds(left)}" for n, left in frozen if left]
        if frozen:
            text += "\n🧊 <b>Заморожены</b>\n" + utils.quote("\n".join(frozen))
        prefix = utils.get_prefix(self.db.raw)
        text += (
            f"\n💡 <i>Выдать доступ: <code>{utils.escape_html(prefix)}sudo add @user</code>, "
            f"<code>{utils.escape_html(prefix)}support</code>, <code>{utils.escape_html(prefix)}owner</code></i>"
        )
        return text

    async def _flood(self, message, args):
        limiter = self.loader.ratelimit
        if len(args) == 1 and args[0].lower() in ("on", "off"):
            limiter.configure(enabled=args[0].lower() == "on")
        elif len(args) == 3 and all(a.isdigit() and int(a) > 0 for a in args):
            limit, window, freeze = map(int, args)
            limiter.configure(limit=limit, window=window, freeze=freeze, enabled=True)
        elif args:
            await utils.answer(
                message,
                utils.card(
                    "❌ <b>Не понял настройку</b>",
                    hint="<code>security flood запросов секунд заморозка</code> (например <code>60 30 300</code>) "
                    "или <code>security flood on|off</code>",
                ),
            )
            return
        await utils.answer(message, self._flood_card())

    def _flood_card(self):
        s = self.loader.ratelimit.settings
        if not s["enabled"]:
            return "⚠️ <b>Защита от флуда выключена</b>"
        return utils.card(
            "❄️ <b>Защита от флуда включена</b>",
            [
                f"📨 Лимит: <code>{s['limit']}</code> запросов за <code>{s['window']} с</code>",
                f"🧊 Заморозка: <code>{s['freeze']} с</code>",
            ],
        )

    async def _unfreeze(self, message, name):
        module = self.loader.get_module(name)
        name = module.name if module else name
        if self.loader.ratelimit.unfreeze(name):
            await utils.answer(message, f"🔥 <b>Модуль {utils.escape_html(name)} разморожен</b>")
        else:
            await utils.answer(message, f"❌ <b>Модуль {utils.escape_html(name)} не заморожен</b>")

    async def _trust(self, message, name, trusted):
        module = self.loader.get_module(name)
        if module is None or module.is_builtin:
            await utils.answer(message, f"❌ <b>Нет стороннего модуля</b> <code>{utils.escape_html(name)}</code>")
            return
        self.loader.guard.set_trusted(module._stem, trusted)
        label = f"<b>{utils.escape_html(module.name)}</b>"
        if trusted:
            await utils.answer(
                message,
                utils.card(
                    f"⚠️ <b>Модулю {label} разрешено всё</b>",
                    TRUST_WARNING,
                    hint="вернуть защиту: <code>security untrust</code>",
                ),
            )
        else:
            await utils.answer(message, f"🛡 <b>Модуль {label} снова под защитой</b>")

    # --- inline: обзор → флуд, защита модулей, права команд, разморозка ---

    @staticmethod
    def _rows(buttons, size=ROW_SIZE):
        return [buttons[i : i + size] for i in range(0, len(buttons), size)]

    def _back(self):
        return [{"text": "◀️ Назад", "callback": self._open_root}, CLOSE]

    async def _root_view(self, status=""):
        text = await self._overview()
        if status:
            text = status + "\n" + text
        buttons = [
            [
                {"text": "❄️ Флуд", "callback": self._open_flood},
                {"text": "🛡 Модули", "callback": self._open_modules},
            ],
            [{"text": "⌨️ Права команд", "callback": self._open_commands}],
        ]
        if self._frozen():
            buttons.append([{"text": "🔥 Разморозить", "callback": self._open_frozen}])
        return text, [*buttons, [CLOSE]]

    def _frozen(self):
        limiter = self.loader.ratelimit
        return [name for name in list(limiter.frozen) if limiter.frozen_for(name)]

    def _flood_view(self, status=""):
        enabled = self.loader.ratelimit.settings["enabled"]
        text = self._flood_card() + (f"\n{status}" if status else "")
        toggle = "🔴 Выключить" if enabled else "🟢 Включить"
        buttons = [
            [{"text": toggle, "callback": self._toggle_flood, "args": (not enabled,)}],
            [{"text": "✍️ Изменить лимиты", "input": "запросов секунд заморозка", "handler": self._input_flood}],
            self._back(),
        ]
        return text, buttons

    def _external(self):
        modules = [m for m in self.loader.modules.values() if not m.is_builtin]
        return sorted(modules, key=lambda m: m.name.lower())

    def _modules_view(self):
        modules = self._external()
        if not modules:
            return "🛡 <b>Сторонних модулей нет</b>", [self._back()]
        trusted = self.loader.guard.trusted()
        lines = [
            f"⚠️ <b>{utils.escape_html(m.name)}</b> — без защиты"
            if m._stem in trusted
            else f"🛡 <b>{utils.escape_html(m.name)}</b> — под защитой"
            for m in modules
        ]
        text = utils.card("🛡 <b>Защита модулей</b>", lines, hint="выберите модуль кнопкой", expandable=len(lines) > 10)
        names = [{"text": m.name, "callback": self._open_module, "args": (m.name,)} for m in modules]
        return text, [*self._rows(names), self._back()]

    def _module_view(self, module, status=""):
        label = f"<b>{utils.escape_html(module.name)}</b>"
        if module._stem in self.loader.guard.trusted():
            text = utils.card(f"⚠️ {label} · без защиты", TRUST_WARNING)
            action = {"text": "🛡 Вернуть защиту", "callback": self._set_trust, "args": (module.name, False)}
        else:
            text = utils.card(f"🛡 {label} · под защитой", "Опасные действия этого модуля блокируются.")
            action = {
                "text": "⚠️ Снять защиту",
                "callback": self._set_trust,
                "args": (module.name, True),
                "confirm": f"🚨 <b>Снять защиту с {label}?</b>\n" + utils.quote(TRUST_WARNING),
            }
        if status:
            text += "\n" + status
        return text, [[action], [{"text": "◀️ Назад", "callback": self._open_modules}, CLOSE]]

    def _commands_view(self, status=""):
        overrides = sorted(self.loader.security.overrides().items())
        items = [f"▸ <code>{utils.escape_html(n)}</code> — {LEVEL_NAMES.get(lv, lv)}" for n, lv in overrides]
        text = utils.card(
            "⌨️ <b>Права команд</b>",
            items or "▸ у всех команд права по умолчанию",
            hint="уровни: <code>owner</code>, <code>sudo</code>, <code>support</code>, <code>everyone</code>, "
            "<code>default</code>",
            expandable=len(items) > 10,
        )
        if status:
            text += "\n" + status
        buttons = [
            [{"text": "✍️ Изменить права", "input": "команда уровень", "handler": self._input_level}],
            self._back(),
        ]
        return text, buttons

    def _frozen_view(self):
        names = self._frozen()
        if not names:
            return "🧊 <b>Замороженных модулей нет</b>", [self._back()]
        buttons = [{"text": name, "callback": self._unfreeze_button, "args": (name,)} for name in names]
        return "🔥 <b>Какой модуль разморозить?</b>", [*self._rows(buttons), self._back()]

    def _find_external(self, name):
        module = self.loader.get_module(name)
        if module is None or module.is_builtin:
            raise InlineError("Модуль уже выгружен")
        return module

    async def _open_root(self, call):
        await call.edit(*await self._root_view())

    async def _open_flood(self, call):
        await call.edit(*self._flood_view())

    async def _open_modules(self, call):
        await call.edit(*self._modules_view())

    async def _open_module(self, call, name):
        await call.edit(*self._module_view(self._find_external(name)))

    async def _open_commands(self, call):
        await call.edit(*self._commands_view())

    async def _open_frozen(self, call):
        await call.edit(*self._frozen_view())

    async def _toggle_flood(self, call, enabled):
        self.loader.ratelimit.configure(enabled=enabled)
        await call.edit(*self._flood_view())

    async def _input_flood(self, call, text):
        args = text.split()
        if len(args) != 3 or not all(a.isdigit() and int(a) > 0 for a in args):
            error = "❌ <b>Нужно три числа:</b> запросов, секунд, заморозка (например <code>60 30 300</code>)"
            await call.edit(*self._flood_view(error))
            return
        limit, window, freeze = map(int, args)
        self.loader.ratelimit.configure(limit=limit, window=window, freeze=freeze, enabled=True)
        await call.edit(*self._flood_view("✅ <b>Сохранено</b>"))

    async def _set_trust(self, call, name, trusted):
        module = self._find_external(name)
        self.loader.guard.set_trusted(module._stem, trusted)
        status = "⚠️ <b>Защита снята</b>" if trusted else "🛡 <b>Защита возвращена</b>"
        await call.edit(*self._module_view(module, status))

    async def _input_level(self, call, text):
        args = text.split()
        reply = self._set_level(*args) if len(args) == 2 else None
        await call.edit(*self._commands_view(reply or "❌ <b>Формат:</b> <code>команда уровень</code>"))

    async def _unfreeze_button(self, call, name):
        self.loader.ratelimit.unfreeze(name)
        await call.edit(*await self._root_view(f"🔥 <b>Модуль {utils.escape_html(name)} разморожен</b>"))

    async def _user(self, user_id):
        if self.client is not None:
            with contextlib.suppress(Exception):
                entity = await self.client.get_entity(user_id)
                name = " ".join(filter(None, (entity.first_name, entity.last_name))) or str(user_id)
                return f'<a href="tg://user?id={user_id}">{utils.escape_html(name)}</a>'
        return f"<code>{user_id}</code>"

    @command("owner", access="owner", emoji="👑")
    async def owner(self, message):
        """[add | del] [пользователь] — владельцы: полный доступ, как у этого аккаунта"""
        await self._group(message, "owner")

    @command("sudo", access="owner", emoji="🛡")
    async def sudo(self, message):
        """[add | del] [пользователь] — sudo: все команды, кроме команд владельца"""
        await self._group(message, "sudo")

    @command("support", access="owner", emoji="🤝")
    async def support(self, message):
        """[add | del] [пользователь] — support: только команды уровня support"""
        await self._group(message, "support")

    async def _group(self, message, group):
        security = self.loader.security
        args = utils.get_args(message)
        if not args:
            members = [f"👤 {await self._user(uid)}" for uid in security.members(group)]
            await utils.answer(
                message,
                utils.card(
                    f"{GROUP_ICONS[group]} <b>{group}</b> · {len(members)}",
                    members or "<i>пусто</i>",
                    hint=f"<code>{group} add|del пользователь</code>",
                ),
            )
            return
        action = args[0].lower()
        if action not in ("add", "del"):
            await utils.answer(
                message, utils.card("❌ <b>Не понял</b>", hint=f"<code>{group} add|del пользователь</code>")
            )
            return

        user = await utils.get_target(message, args[1] if len(args) > 1 else "")
        if user is None or getattr(user, "id", None) is None:
            await utils.answer(
                message,
                utils.card(
                    "❌ <b>Пользователь не найден</b>", hint="ответьте на его сообщение или укажите @username/id"
                ),
            )
            return
        if user.id == security.me_id:
            await utils.answer(message, "👑 <b>Этот аккаунт и так владелец</b>")
            return
        label = await self._user(user.id)
        icon = GROUP_ICONS[group]
        if action == "add":
            changed = security.add(group, user.id)
            text = f"{icon} {label} <b>добавлен в {group}</b>" if changed else f"❌ {label} <b>уже в {group}</b>"
        else:
            changed = security.remove(group, user.id)
            text = f"🗑 {label} <b>удалён из {group}</b>" if changed else f"❌ {label} <b>нет в {group}</b>"
        await utils.answer(message, text)
