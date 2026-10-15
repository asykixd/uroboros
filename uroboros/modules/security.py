import contextlib

from uroboros import Module, command, utils
from uroboros.errors import InlineError
from uroboros.ratelimit import format_seconds
from uroboros.security import GROUPS, LEVELS

GROUP_ICONS = {"owner": "👑", "sudo": "🛡", "support": "🤝"}
ROW_SIZE = 3
LEVELS_HINT = "<code>owner</code>, <code>sudo</code>, <code>support</code>, <code>everyone</code>, <code>default</code>"


class Security(Module):
    """Access: owners, sudo, support and command permissions"""

    strings = {
        "usage": (
            "❌ <b>Didn't understand</b>\n"
            "<blockquote>🔐 <code>security</code> — overview\n"
            "⌨️ <code>security command level</code> — command permissions\n"
            "❄️ <code>security flood ...</code> — flood protection\n"
            "🛡 <code>security trust|untrust module</code> — module protection</blockquote>\n"
            "💡 <i>levels: " + LEVELS_HINT + "</i>"
        ),
        "levels_hint": "levels: " + LEVELS_HINT,
        "level_owner": "owners",
        "level_sudo": "sudo",
        "level_support": "support",
        "level_everyone": "everyone",
        "no_command": "❌ <b>No command</b> <code>{name}</code>",
        "level_changed": "🔐 <b>Permissions changed</b> · <code>{name}</code> — {level}",
        "by_default": " (default)",
        "this_account": "this account",
        "title": "🔐 <b>Access and protection</b>",
        "overrides": "⌨️ <b>Changed permissions</b>",
        "flood_rule": "at most {limit} module requests in {window} s, otherwise a {freeze} s freeze",
        "off": "off",
        "flood_line": "❄️ <b>Flood protection:</b> {state}",
        "untrusted_title": "🛡 <b>No runtime protection</b>",
        "frozen_left": "<b>{name}</b> — {left} left",
        "frozen_title": "🧊 <b>Frozen</b>",
        "grant_hint": (
            "💡 <i>Grant access: <code>{prefix}sudo add @user</code>, <code>{prefix}support</code>, "
            "<code>{prefix}owner</code></i>"
        ),
        "bad_flood": "❌ <b>Didn't understand the setting</b>",
        "bad_flood_hint": (
            "<code>security flood requests seconds freeze</code> (for example <code>60 30 300</code>) "
            "or <code>security flood on|off</code>"
        ),
        "flood_disabled": "⚠️ <b>Flood protection is off</b>",
        "flood_enabled": "❄️ <b>Flood protection is on</b>",
        "flood_limit": "📨 Limit: <code>{limit}</code> requests in <code>{window} s</code>",
        "flood_freeze": "🧊 Freeze: <code>{freeze} s</code>",
        "unfrozen": "🔥 <b>Module {name} unfrozen</b>",
        "not_frozen": "❌ <b>Module {name} isn't frozen</b>",
        "no_external": "❌ <b>No third-party module</b> <code>{name}</code>",
        "trusted": "⚠️ <b>Module {name} is allowed everything</b>",
        "trust_warning": (
            "Runtime protection no longer restricts it: it can read the session, terminate sessions and change "
            "the password."
        ),
        "untrust_hint": "restore protection: <code>security untrust</code>",
        "protected_again": "🛡 <b>Module {name} is protected again</b>",
        "back": "◀️ Back",
        "close": "✖️ Close",
        "btn_flood": "❄️ Flood",
        "btn_modules": "🛡 Modules",
        "btn_commands": "⌨️ Command permissions",
        "btn_unfreeze": "🔥 Unfreeze",
        "turn_off": "🔴 Turn off",
        "turn_on": "🟢 Turn on",
        "btn_limits": "✍️ Change limits",
        "limits_prompt": "requests seconds freeze",
        "no_externals": "🛡 <b>No third-party modules</b>",
        "unprotected_line": "⚠️ <b>{name}</b> — unprotected",
        "protected_line": "🛡 <b>{name}</b> — protected",
        "modules_title": "🛡 <b>Module protection</b>",
        "pick_module": "pick a module with a button",
        "unprotected": "⚠️ <b>{name}</b> · unprotected",
        "protected": "🛡 <b>{name}</b> · protected",
        "blocked_note": "Dangerous actions of this module are blocked.",
        "btn_protect": "🛡 Restore protection",
        "btn_unprotect": "⚠️ Remove protection",
        "confirm_unprotect": "🚨 <b>Remove protection from <b>{name}</b>?</b>",
        "commands_title": "⌨️ <b>Command permissions</b>",
        "all_default": "▸ all commands have default permissions",
        "btn_level": "✍️ Change permissions",
        "level_prompt": "command level",
        "no_frozen": "🧊 <b>No frozen modules</b>",
        "which_unfreeze": "🔥 <b>Which module to unfreeze?</b>",
        "unloaded": "The module is already unloaded",
        "need_three": "❌ <b>Three numbers needed:</b> requests, seconds, freeze (for example <code>60 30 300</code>)",
        "saved": "✅ <b>Saved</b>",
        "unprotected_status": "⚠️ <b>Protection removed</b>",
        "protected_status": "🛡 <b>Protection restored</b>",
        "level_format": "❌ <b>Format:</b> <code>command level</code>",
        "empty": "<i>empty</i>",
        "group_hint": "<code>{group} add|del user</code>",
        "unknown": "❌ <b>Didn't understand</b>",
        "user_not_found": "❌ <b>User not found</b>",
        "user_hint": "reply to their message or give @username/id",
        "already_owner": "👑 <b>This account is the owner already</b>",
        "added": "{label} <b>added to {group}</b>",
        "already_in": "❌ {label} <b>is already in {group}</b>",
        "removed": "🗑 {label} <b>removed from {group}</b>",
        "not_in": "❌ {label} <b>isn't in {group}</b>",
    }
    strings_ru = {
        "_cls_doc": "Доступ: владельцы, sudo, support и права на команды",
        "_cmd_doc_security": (
            "[команда уровень | flood ... | unfreeze модуль | trust/untrust модуль] — доступ, права команд и защита"
        ),
        "_cmd_doc_owner": "[add | del] [пользователь] — владельцы: полный доступ, как у этого аккаунта",
        "_cmd_doc_sudo": "[add | del] [пользователь] — sudo: все команды, кроме команд владельца",
        "_cmd_doc_support": "[add | del] [пользователь] — support: только команды уровня support",
        "usage": (
            "❌ <b>Не понял</b>\n"
            "<blockquote>🔐 <code>security</code> — обзор\n"
            "⌨️ <code>security команда уровень</code> — права команды\n"
            "❄️ <code>security flood ...</code> — защита от флуда\n"
            "🛡 <code>security trust|untrust модуль</code> — защита модуля</blockquote>\n"
            "💡 <i>уровни: " + LEVELS_HINT + "</i>"
        ),
        "levels_hint": "уровни: " + LEVELS_HINT,
        "level_owner": "владельцы",
        "level_sudo": "sudo",
        "level_support": "support",
        "level_everyone": "все",
        "no_command": "❌ <b>Нет команды</b> <code>{name}</code>",
        "level_changed": "🔐 <b>Права изменены</b> · <code>{name}</code> — {level}",
        "by_default": " (по умолчанию)",
        "this_account": "этот аккаунт",
        "title": "🔐 <b>Доступ и защита</b>",
        "overrides": "⌨️ <b>Изменённые права</b>",
        "flood_rule": "не больше {limit} запросов модуля за {window} с, иначе заморозка на {freeze} с",
        "off": "выключена",
        "flood_line": "❄️ <b>Защита от флуда:</b> {state}",
        "untrusted_title": "🛡 <b>Без защиты во время работы</b>",
        "frozen_left": "<b>{name}</b> — ещё {left}",
        "frozen_title": "🧊 <b>Заморожены</b>",
        "grant_hint": (
            "💡 <i>Выдать доступ: <code>{prefix}sudo add @user</code>, <code>{prefix}support</code>, "
            "<code>{prefix}owner</code></i>"
        ),
        "bad_flood": "❌ <b>Не понял настройку</b>",
        "bad_flood_hint": (
            "<code>security flood запросов секунд заморозка</code> (например <code>60 30 300</code>) "
            "или <code>security flood on|off</code>"
        ),
        "flood_disabled": "⚠️ <b>Защита от флуда выключена</b>",
        "flood_enabled": "❄️ <b>Защита от флуда включена</b>",
        "flood_limit": "📨 Лимит: <code>{limit}</code> запросов за <code>{window} с</code>",
        "flood_freeze": "🧊 Заморозка: <code>{freeze} с</code>",
        "unfrozen": "🔥 <b>Модуль {name} разморожен</b>",
        "not_frozen": "❌ <b>Модуль {name} не заморожен</b>",
        "no_external": "❌ <b>Нет стороннего модуля</b> <code>{name}</code>",
        "trusted": "⚠️ <b>Модулю {name} разрешено всё</b>",
        "trust_warning": (
            "Защита во время работы его больше не ограничивает: он может читать сессию, завершать сеансы и менять "
            "пароль."
        ),
        "untrust_hint": "вернуть защиту: <code>security untrust</code>",
        "protected_again": "🛡 <b>Модуль {name} снова под защитой</b>",
        "back": "◀️ Назад",
        "close": "✖️ Закрыть",
        "btn_flood": "❄️ Флуд",
        "btn_modules": "🛡 Модули",
        "btn_commands": "⌨️ Права команд",
        "btn_unfreeze": "🔥 Разморозить",
        "turn_off": "🔴 Выключить",
        "turn_on": "🟢 Включить",
        "btn_limits": "✍️ Изменить лимиты",
        "limits_prompt": "запросов секунд заморозка",
        "no_externals": "🛡 <b>Сторонних модулей нет</b>",
        "unprotected_line": "⚠️ <b>{name}</b> — без защиты",
        "protected_line": "🛡 <b>{name}</b> — под защитой",
        "modules_title": "🛡 <b>Защита модулей</b>",
        "pick_module": "выберите модуль кнопкой",
        "unprotected": "⚠️ <b>{name}</b> · без защиты",
        "protected": "🛡 <b>{name}</b> · под защитой",
        "blocked_note": "Опасные действия этого модуля блокируются.",
        "btn_protect": "🛡 Вернуть защиту",
        "btn_unprotect": "⚠️ Снять защиту",
        "confirm_unprotect": "🚨 <b>Снять защиту с <b>{name}</b>?</b>",
        "commands_title": "⌨️ <b>Права команд</b>",
        "all_default": "▸ у всех команд права по умолчанию",
        "btn_level": "✍️ Изменить права",
        "level_prompt": "команда уровень",
        "no_frozen": "🧊 <b>Замороженных модулей нет</b>",
        "which_unfreeze": "🔥 <b>Какой модуль разморозить?</b>",
        "unloaded": "Модуль уже выгружен",
        "need_three": "❌ <b>Нужно три числа:</b> запросов, секунд, заморозка (например <code>60 30 300</code>)",
        "saved": "✅ <b>Сохранено</b>",
        "unprotected_status": "⚠️ <b>Защита снята</b>",
        "protected_status": "🛡 <b>Защита возвращена</b>",
        "level_format": "❌ <b>Формат:</b> <code>команда уровень</code>",
        "empty": "<i>пусто</i>",
        "group_hint": "<code>{group} add|del пользователь</code>",
        "unknown": "❌ <b>Не понял</b>",
        "user_not_found": "❌ <b>Пользователь не найден</b>",
        "user_hint": "ответьте на его сообщение или укажите @username/id",
        "already_owner": "👑 <b>Этот аккаунт и так владелец</b>",
        "added": "{label} <b>добавлен в {group}</b>",
        "already_in": "❌ {label} <b>уже в {group}</b>",
        "removed": "🗑 {label} <b>удалён из {group}</b>",
        "not_in": "❌ {label} <b>нет в {group}</b>",
    }

    def _level(self, level):
        return self.strings.get(f"level_{level}", level)

    @command("security", access="owner", emoji="🔐")
    async def security(self, message):
        """[command level | flood ... | unfreeze module | trust/untrust module] — access, permissions, protection"""
        args = utils.get_args(message)
        if not args:
            if self.inline.available:
                try:
                    await self.inline.form(message, *await self._root_view())
                    return
                except InlineError:
                    pass  # e.g. inline bots are banned in this chat: answer with text
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
            await utils.answer(message, self.strings("usage"))
            return

        await utils.answer(message, self._set_level(args[0], args[1]) or self.strings("usage"))

    def _set_level(self, name, level):
        """Changes a command's level; the reply for the user, or None if the level is unknown."""
        name, level = name.lower().removeprefix(utils.get_prefix(self.db.raw)), level.lower()
        cmd = self.loader.get_command(name)
        if cmd is None:
            return self.strings("no_command", name=name)
        if level not in (*LEVELS, "default"):
            return None
        security = self.loader.security
        security.set_required(cmd.name, None if level == "default" else level)
        required = security.required(cmd)
        return self.strings("level_changed", name=cmd.name, level=self._level(required)) + (
            self.strings("by_default") if required == cmd.info.access and level == "default" else ""
        )

    async def _overview(self):
        security = self.loader.security
        lines = []
        for group in GROUPS:
            members = security.members(group)
            names = ", ".join([await self._user(uid) for uid in members]) or "—"
            if group == "owner":
                names = self.strings("this_account") + (f", {names}" if members else "")
            lines.append(f"{GROUP_ICONS[group]} <b>{group}:</b> {names}")
        text = utils.card(self.strings("title"), lines)

        overrides = security.overrides()
        if overrides:
            items = [
                f"▸ <code>{utils.escape_html(n)}</code> — {self._level(lv)}" for n, lv in sorted(overrides.items())
            ]
            text += f"\n{self.strings('overrides')}\n" + utils.quote("\n".join(items), expandable=len(items) > 10)
        limiter = self.loader.ratelimit
        settings = limiter.settings
        flood = (
            self.strings("flood_rule", limit=settings["limit"], window=settings["window"], freeze=settings["freeze"])
            if settings["enabled"]
            else self.strings("off")
        )
        text += "\n" + self.strings("flood_line", state=flood)
        trusted = sorted(self.loader.guard.trusted())
        if trusted:
            names = {m._stem: m.name for m in self.loader.modules.values()}
            items = [f"<b>{utils.escape_html(names.get(stem, stem))}</b>" for stem in trusted]
            text += f"\n{self.strings('untrusted_title')}\n" + utils.quote(", ".join(items))
        frozen = [(name, limiter.frozen_for(name)) for name in list(limiter.frozen)]
        frozen = [self.strings("frozen_left", name=n, left=format_seconds(left)) for n, left in frozen if left]
        if frozen:
            text += f"\n{self.strings('frozen_title')}\n" + utils.quote("\n".join(frozen))
        return text + "\n" + self.strings("grant_hint", prefix=utils.get_prefix(self.db.raw))

    async def _flood(self, message, args):
        limiter = self.loader.ratelimit
        if len(args) == 1 and args[0].lower() in ("on", "off"):
            limiter.configure(enabled=args[0].lower() == "on")
        elif len(args) == 3 and all(a.isdigit() and int(a) > 0 for a in args):
            limit, window, freeze = map(int, args)
            limiter.configure(limit=limit, window=window, freeze=freeze, enabled=True)
        elif args:
            await utils.answer(message, utils.card(self.strings("bad_flood"), hint=self.strings("bad_flood_hint")))
            return
        await utils.answer(message, self._flood_card())

    def _flood_card(self):
        s = self.loader.ratelimit.settings
        if not s["enabled"]:
            return self.strings("flood_disabled")
        return utils.card(
            self.strings("flood_enabled"),
            [
                self.strings("flood_limit", limit=s["limit"], window=s["window"]),
                self.strings("flood_freeze", freeze=s["freeze"]),
            ],
        )

    async def _unfreeze(self, message, name):
        module = self.loader.get_module(name)
        name = module.name if module else name
        key = "unfrozen" if self.loader.ratelimit.unfreeze(name) else "not_frozen"
        await utils.answer(message, self.strings(key, name=name))

    async def _trust(self, message, name, trusted):
        module = self.loader.get_module(name)
        if module is None or module.is_builtin:
            await utils.answer(message, self.strings("no_external", name=name))
            return
        self.loader.guard.set_trusted(module._stem, trusted)
        label = utils.Html(f"<b>{utils.escape_html(module.name)}</b>")
        if trusted:
            await utils.answer(
                message,
                utils.card(
                    self.strings("trusted", name=label),
                    self.strings("trust_warning"),
                    hint=self.strings("untrust_hint"),
                ),
            )
        else:
            await utils.answer(message, self.strings("protected_again", name=label))

    # --- inline: overview → flood, module protection, command permissions, unfreezing ---

    @staticmethod
    def _rows(buttons, size=ROW_SIZE):
        return [buttons[i : i + size] for i in range(0, len(buttons), size)]

    @property
    def _close(self):
        return {"text": self.strings("close"), "action": "close"}

    def _back(self):
        return [{"text": self.strings("back"), "callback": self._open_root}, self._close]

    async def _root_view(self, status=""):
        text = await self._overview()
        if status:
            text = status + "\n" + text
        buttons = [
            [
                {"text": self.strings("btn_flood"), "callback": self._open_flood},
                {"text": self.strings("btn_modules"), "callback": self._open_modules},
            ],
            [{"text": self.strings("btn_commands"), "callback": self._open_commands}],
        ]
        if self._frozen():
            buttons.append([{"text": self.strings("btn_unfreeze"), "callback": self._open_frozen}])
        return text, [*buttons, [self._close]]

    def _frozen(self):
        limiter = self.loader.ratelimit
        return [name for name in list(limiter.frozen) if limiter.frozen_for(name)]

    def _flood_view(self, status=""):
        enabled = self.loader.ratelimit.settings["enabled"]
        text = self._flood_card() + (f"\n{status}" if status else "")
        toggle = self.strings("turn_off") if enabled else self.strings("turn_on")
        limits = {"text": self.strings("btn_limits"), "input": self.strings("limits_prompt")}
        buttons = [
            [{"text": toggle, "callback": self._toggle_flood, "args": (not enabled,)}],
            [{**limits, "handler": self._input_flood}],
            self._back(),
        ]
        return text, buttons

    def _external(self):
        modules = [m for m in self.loader.modules.values() if not m.is_builtin]
        return sorted(modules, key=lambda m: m.name.lower())

    def _modules_view(self):
        modules = self._external()
        if not modules:
            return self.strings("no_externals"), [self._back()]
        trusted = self.loader.guard.trusted()
        lines = [
            self.strings("unprotected_line" if m._stem in trusted else "protected_line", name=m.name) for m in modules
        ]
        text = utils.card(
            self.strings("modules_title"), lines, hint=self.strings("pick_module"), expandable=len(lines) > 10
        )
        names = [{"text": m.name, "callback": self._open_module, "args": (m.name,)} for m in modules]
        return text, [*self._rows(names), self._back()]

    def _module_view(self, module, status=""):
        warning = self.strings("trust_warning")
        if module._stem in self.loader.guard.trusted():
            text = utils.card(self.strings("unprotected", name=module.name), warning)
            action = {"text": self.strings("btn_protect"), "callback": self._set_trust, "args": (module.name, False)}
        else:
            text = utils.card(self.strings("protected", name=module.name), self.strings("blocked_note"))
            action = {
                "text": self.strings("btn_unprotect"),
                "callback": self._set_trust,
                "args": (module.name, True),
                "confirm": self.strings("confirm_unprotect", name=module.name) + "\n" + utils.quote(warning),
            }
        if status:
            text += "\n" + status
        back = {"text": self.strings("back"), "callback": self._open_modules}
        return text, [[action], [back, self._close]]

    def _commands_view(self, status=""):
        overrides = sorted(self.loader.security.overrides().items())
        items = [f"▸ <code>{utils.escape_html(n)}</code> — {self._level(lv)}" for n, lv in overrides]
        text = utils.card(
            self.strings("commands_title"),
            items or self.strings("all_default"),
            hint=self.strings("levels_hint"),
            expandable=len(items) > 10,
        )
        if status:
            text += "\n" + status
        level = {"text": self.strings("btn_level"), "input": self.strings("level_prompt")}
        return text, [[{**level, "handler": self._input_level}], self._back()]

    def _frozen_view(self):
        names = self._frozen()
        if not names:
            return self.strings("no_frozen"), [self._back()]
        buttons = [{"text": name, "callback": self._unfreeze_button, "args": (name,)} for name in names]
        return self.strings("which_unfreeze"), [*self._rows(buttons), self._back()]

    def _find_external(self, name):
        module = self.loader.get_module(name)
        if module is None or module.is_builtin:
            raise InlineError(self.strings("unloaded"))
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
            await call.edit(*self._flood_view(self.strings("need_three")))
            return
        limit, window, freeze = map(int, args)
        self.loader.ratelimit.configure(limit=limit, window=window, freeze=freeze, enabled=True)
        await call.edit(*self._flood_view(self.strings("saved")))

    async def _set_trust(self, call, name, trusted):
        module = self._find_external(name)
        self.loader.guard.set_trusted(module._stem, trusted)
        status = self.strings("unprotected_status") if trusted else self.strings("protected_status")
        await call.edit(*self._module_view(module, status))

    async def _input_level(self, call, text):
        args = text.split()
        reply = self._set_level(*args) if len(args) == 2 else None
        await call.edit(*self._commands_view(reply or self.strings("level_format")))

    async def _unfreeze_button(self, call, name):
        self.loader.ratelimit.unfreeze(name)
        await call.edit(*await self._root_view(self.strings("unfrozen", name=name)))

    async def _user(self, user_id):
        if self.client is not None:
            with contextlib.suppress(Exception):
                entity = await self.client.get_entity(user_id)
                name = " ".join(filter(None, (entity.first_name, entity.last_name))) or str(user_id)
                return f'<a href="tg://user?id={user_id}">{utils.escape_html(name)}</a>'
        return f"<code>{user_id}</code>"

    @command("owner", access="owner", emoji="👑")
    async def owner(self, message):
        """[add | del] [user] — owners: full access, like this account"""
        await self._group(message, "owner")

    @command("sudo", access="owner", emoji="🛡")
    async def sudo(self, message):
        """[add | del] [user] — sudo: all commands except owner commands"""
        await self._group(message, "sudo")

    @command("support", access="owner", emoji="🤝")
    async def support(self, message):
        """[add | del] [user] — support: only support-level commands"""
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
                    members or self.strings("empty"),
                    hint=self.strings("group_hint", group=group),
                ),
            )
            return
        action = args[0].lower()
        if action not in ("add", "del"):
            await utils.answer(
                message, utils.card(self.strings("unknown"), hint=self.strings("group_hint", group=group))
            )
            return

        user = await utils.get_target(message, args[1] if len(args) > 1 else "")
        if user is None or getattr(user, "id", None) is None:
            await utils.answer(message, utils.card(self.strings("user_not_found"), hint=self.strings("user_hint")))
            return
        if user.id == security.me_id:
            await utils.answer(message, self.strings("already_owner"))
            return
        label = utils.Html(await self._user(user.id))
        if action == "add":
            changed = security.add(group, user.id)
            key = "added" if changed else "already_in"
        else:
            changed = security.remove(group, user.id)
            key = "removed" if changed else "not_in"
        text = self.strings(key, label=label, group=group)
        await utils.answer(message, f"{GROUP_ICONS[group]} {text}" if key == "added" else text)
