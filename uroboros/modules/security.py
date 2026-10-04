import contextlib

from uroboros import Module, command, utils
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


class Security(Module):
    """Доступ: владельцы, sudo, support и права на команды"""

    @command("security", access="owner", emoji="🔐")
    async def security(self, message):
        """[команда уровень | flood ... | unfreeze модуль | trust/untrust модуль] — доступ, права команд и защита"""
        args = utils.get_args(message)
        if not args:
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

        name, level = args[0].lower().removeprefix(utils.get_prefix(self.db.raw)), args[1].lower()
        cmd = self.loader.get_command(name)
        if cmd is None:
            await utils.answer(message, f"❌ <b>Нет команды</b> <code>{utils.escape_html(name)}</code>")
            return
        if level not in (*LEVELS, "default"):
            await utils.answer(message, USAGE)
            return
        security = self.loader.security
        security.set_required(cmd.name, None if level == "default" else level)
        required = security.required(cmd)
        await utils.answer(
            message,
            f"🔐 <b>Права изменены</b> · <code>{cmd.name}</code> — {LEVEL_NAMES[required]}"
            + (" (по умолчанию)" if required == cmd.info.access and level == "default" else ""),
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
        s = limiter.settings
        if not s["enabled"]:
            await utils.answer(message, "⚠️ <b>Защита от флуда выключена</b>")
            return
        await utils.answer(
            message,
            utils.card(
                "❄️ <b>Защита от флуда включена</b>",
                [
                    f"📨 Лимит: <code>{s['limit']}</code> запросов за <code>{s['window']} с</code>",
                    f"🧊 Заморозка: <code>{s['freeze']} с</code>",
                ],
            ),
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
                    "Защита во время работы его больше не ограничивает: он может читать сессию, "
                    "завершать сеансы и менять пароль.",
                    hint="вернуть защиту: <code>security untrust</code>",
                ),
            )
        else:
            await utils.answer(message, f"🛡 <b>Модуль {label} снова под защитой</b>")

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
