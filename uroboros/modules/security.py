import contextlib

from uroboros import Module, command, utils
from uroboros.ratelimit import format_seconds
from uroboros.security import GROUPS, LEVEL_NAMES, LEVELS

USAGE = (
    "❌ Использование: <code>security</code>, <code>security команда уровень</code>, "
    "уровни: <code>owner</code>, <code>sudo</code>, <code>support</code>, <code>everyone</code>, <code>default</code>"
)


class Security(Module):
    """Доступ: владельцы, sudo, support и права на команды"""

    @command("security", access="owner")
    async def security(self, message):
        """[команда уровень | flood ... | unfreeze модуль] — доступ, права команд и защита от флуда"""
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
        if len(args) != 2:
            await utils.answer(message, USAGE)
            return

        name, level = args[0].lower().removeprefix(utils.get_prefix(self.db.raw)), args[1].lower()
        cmd = self.loader.get_command(name)
        if cmd is None:
            await utils.answer(message, f"❌ Команды <code>{utils.escape_html(name)}</code> нет")
            return
        if level not in (*LEVELS, "default"):
            await utils.answer(message, USAGE)
            return
        security = self.loader.security
        security.set_required(cmd.name, None if level == "default" else level)
        required = security.required(cmd)
        await utils.answer(
            message,
            f"✅ <code>{cmd.name}</code>: {LEVEL_NAMES[required]}"
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
            lines.append(f"<b>{group}:</b> {names}")
        text = "🔐 <b>Доступ</b>\n" + utils.quote("\n".join(lines))

        overrides = security.overrides()
        if overrides:
            items = [
                f"<code>{utils.escape_html(n)}</code> — {LEVEL_NAMES.get(lv, lv)}"
                for n, lv in sorted(overrides.items())
            ]
            text += "\n<b>Изменённые права</b>\n" + utils.quote("\n".join(items), expandable=len(items) > 10)
        limiter = self.loader.ratelimit
        settings = limiter.settings
        flood = (
            f"не больше {settings['limit']} запросов модуля за {settings['window']} с, "
            f"иначе заморозка на {settings['freeze']} с"
            if settings["enabled"]
            else "выключена"
        )
        text += f"\n<b>Защита от флуда:</b> {flood}"
        frozen = [(name, limiter.frozen_for(name)) for name in list(limiter.frozen)]
        frozen = [f"<b>{utils.escape_html(n)}</b> — ещё {format_seconds(left)}" for n, left in frozen if left]
        if frozen:
            text += "\n<b>Заморожены</b>\n" + utils.quote("\n".join(frozen))
        prefix = utils.get_prefix(self.db.raw)
        text += (
            f"\n<i>Группы:</i> <code>{prefix}sudo add @user</code>, "
            f"<code>{prefix}support</code>, <code>{prefix}owner</code>"
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
                "❌ Использование: <code>security flood запросов секунд заморозка</code> "
                "(например <code>60 30 300</code>) или <code>security flood on|off</code>",
            )
            return
        s = limiter.settings
        if not s["enabled"]:
            await utils.answer(message, "✅ Защита от флуда выключена")
            return
        await utils.answer(
            message,
            "✅ <b>Защита от флуда</b>\n"
            + utils.quote(
                f"Сторонний модуль, отправивший больше {s['limit']} запросов за {s['window']} с, "
                f"замораживается на {s['freeze']} с"
            ),
        )

    async def _unfreeze(self, message, name):
        module = self.loader.get_module(name)
        name = module.name if module else name
        if self.loader.ratelimit.unfreeze(name):
            await utils.answer(message, f"✅ Модуль <b>{utils.escape_html(name)}</b> разморожен")
        else:
            await utils.answer(message, f"❌ Модуль <b>{utils.escape_html(name)}</b> не заморожен")

    async def _user(self, user_id):
        if self.client is not None:
            with contextlib.suppress(Exception):
                entity = await self.client.get_entity(user_id)
                name = " ".join(filter(None, (entity.first_name, entity.last_name))) or str(user_id)
                return f'<a href="tg://user?id={user_id}">{utils.escape_html(name)}</a>'
        return f"<code>{user_id}</code>"

    @command("owner", access="owner")
    async def owner(self, message):
        """[add | del] [пользователь] — владельцы: полный доступ, как у этого аккаунта"""
        await self._group(message, "owner")

    @command("sudo", access="owner")
    async def sudo(self, message):
        """[add | del] [пользователь] — sudo: все команды, кроме команд владельца"""
        await self._group(message, "sudo")

    @command("support", access="owner")
    async def support(self, message):
        """[add | del] [пользователь] — support: только команды уровня support"""
        await self._group(message, "support")

    async def _group(self, message, group):
        security = self.loader.security
        args = utils.get_args(message)
        if not args:
            members = [await self._user(uid) for uid in security.members(group)]
            body = utils.quote("\n".join(members)) if members else "\n<i>пусто</i>"
            await utils.answer(message, f"🔐 <b>{group}</b> · {len(members)}" + ("\n" + body if members else body))
            return
        action = args[0].lower()
        if action not in ("add", "del"):
            await utils.answer(message, f"❌ Использование: <code>{group} add|del пользователь</code>")
            return

        user = await utils.get_target(message, args[1] if len(args) > 1 else "")
        if user is None or getattr(user, "id", None) is None:
            await utils.answer(message, "❌ Пользователь не найден: ответьте на его сообщение или укажите @username/id")
            return
        if user.id == security.me_id:
            await utils.answer(message, "❌ Этот аккаунт и так владелец")
            return
        label = await self._user(user.id)
        if action == "add":
            changed = security.add(group, user.id)
            text = f"✅ {label} добавлен в <b>{group}</b>" if changed else f"❌ {label} уже в <b>{group}</b>"
        else:
            changed = security.remove(group, user.id)
            text = f"🗑 {label} удалён из <b>{group}</b>" if changed else f"❌ {label} нет в <b>{group}</b>"
        await utils.answer(message, text)
