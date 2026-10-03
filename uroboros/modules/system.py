import asyncio
import contextlib
import io
import logging
import platform
import time

import telethon

import uroboros
from uroboros import Module, command, logs, loop, updater, utils
from uroboros.errors import InlineError

CANCEL = {"text": "Отмена", "action": "close"}
CHECK_EVERY = 24 * 3600
DOCKER_UPDATE = "git pull &amp;&amp; docker compose up -d --build"


class System(Module):
    """Состояние, перезапуск и обновление"""

    async def on_load(self):
        # Если перезапуск инициирован командой — отчитываемся в том же сообщении.
        pending = self.db.get("restart")
        if not pending or self.client is None:
            return
        self.db.delete("restart")
        chat_id, message_id, started = pending
        with contextlib.suppress(Exception):
            await self.client.edit_message(chat_id, message_id, f"✅ Перезапущено за {time.time() - started:.1f} с")

    @command("ping", access="support")
    async def ping(self, message):
        """— задержка до Telegram"""
        start = time.perf_counter()
        await utils.answer(message, "⏱ <b>ping:</b> ...")
        elapsed = (time.perf_counter() - start) * 1000
        await utils.answer(message, f"⏱ <b>ping:</b> <code>{elapsed:.0f}ms</code>")

    @command("info", access="support")
    async def info(self, message):
        """— информация о юзерботе"""
        me = await self.client.get_me()
        await utils.answer(
            message,
            f"🐍 <b>Uroboros</b> <code>{uroboros.__version__}</code>\n"
            + utils.quote(
                f"<b>Аккаунт:</b> {utils.escape_html(me.first_name)}\n"
                f"<b>Аптайм:</b> <code>{utils.format_duration(time.time() - utils.START_TIME)}</code>\n"
                f"<b>Модули:</b> <code>{len(self.loader.modules)}</code> · "
                f"<b>команды:</b> <code>{len(self.loader.commands)}</code>\n"
                f"<b>Префикс:</b> <code>{utils.escape_html(utils.get_prefix(self.db.raw))}</code>"
            )
            + utils.quote(
                f"<b>Python</b> <code>{platform.python_version()}</code> · "
                f"<b>Telethon</b> <code>{telethon.__version__}</code>\n"
                f"<b>Система:</b> <code>{utils.escape_html(platform.platform())}</code>"
            ),
        )

    @command("logs", access="owner")
    async def show_logs(self, message):
        """[уровень] — прислать логи файлом в «Избранное» (debug, info, warning, error, critical)"""
        arg = utils.get_args_raw(message).strip()
        level = logs.parse_level(arg) if arg else logging.NOTSET
        if level is None:
            await utils.answer(
                message,
                "❌ Уровни: <code>debug</code>, <code>info</code>, <code>warning</code>, "
                "<code>error</code>, <code>critical</code>",
            )
            return
        if not logs.log_files():
            await utils.answer(message, "❌ Логи в файл не пишутся")
            return

        lines = await asyncio.to_thread(logs.read, level)
        level_name = logging.getLevelName(level) if level else "все"
        if not lines:
            await utils.answer(message, f"📄 В логах нет записей уровня <code>{level_name}</code>")
            return

        file = io.BytesIO("\n".join(lines).encode())
        file.name = "uroboros.log"
        # В логах бывают тексты сообщений и пути — в чужой чат их не шлём.
        await self.client.send_file(
            "me",
            file,
            caption=f"📄 <b>Логи</b> · уровень <code>{level_name}</code> · строк: {len(lines)}",
            parse_mode="html",
        )
        await utils.answer(message, "📄 Логи отправлены в «Избранное»")

    @command("restart", access="owner")
    async def restart(self, message):
        """— перезапустить юзербот"""
        msg = await utils.answer(message, "🔄 Перезапуск...")
        self.db.set("restart", [msg.chat_id, msg.id, time.time()])
        await utils.restart(self.client)

    @command("update", access="owner")
    async def update(self, message):
        """[-f | channel stable|beta | notify on|off] — обновиться: список изменений и подтверждение"""
        args = utils.get_args(message)
        if args and args[0] == "channel":
            await self._channel(message, args[1:])
            return
        if args and args[0] == "notify":
            await self._notify(message, args[1:])
            return
        if updater.in_docker():
            await utils.answer(message, f"❌ В Docker обновляйтесь образом: <code>{DOCKER_UPDATE}</code>")
            return
        if not updater.is_git_checkout():
            await utils.answer(message, "❌ Uroboros установлен не из git-репозитория")
            return

        await utils.answer(message, "⏳ Проверяю обновления...")
        update = await updater.check(self._get_channel())
        if update is None:
            await utils.answer(message, f"✅ Установлена последняя версия <i>(канал {self._get_channel()})</i>")
            return
        if args and args[0] == "-f":
            await self._install(update, lambda text: utils.answer(message, text), message)
            return

        text = self._changelog(update)
        if self.inline.available:
            buttons = [[{"text": "✅ Обновить", "callback": self._install_pressed, "args": (update,)}, CANCEL]]
            try:
                await self.inline.form(message, text, buttons)
                return
            except InlineError:
                pass  # например, в чате запрещены inline-боты
        prefix = utils.get_prefix(self.db.raw)
        await utils.answer(message, text + f"\nУстановить: <code>{utils.escape_html(prefix)}update -f</code>")

    def _get_channel(self):
        return self.db.get("channel", updater.DEFAULT_CHANNEL)

    @staticmethod
    def _changelog(update):
        shown = update.commits[: updater.MAX_CHANGELOG]
        lines = [
            f"<code>{utils.escape_html(c.split(' ', 1)[0])}</code> {utils.escape_html(c.split(' ', 1)[-1])}"
            for c in shown
        ]
        if len(update.commits) > len(shown):
            lines.append("…")
        count = f"{len(shown)}+" if len(update.commits) > len(shown) else str(len(shown))
        return (
            f"🆕 <b>Доступно обновление</b> · {utils.escape_html(update.label)} · изменений: {count}\n"
            + utils.quote("\n".join(lines) or "без описания", expandable=len(lines) > 10)
        )

    async def _install_pressed(self, call, update):
        await call.edit("⏳ Обновление...", None)

        async def report(text):
            await call.edit(text, None)

        await self._install(update, report, None)

    async def _install(self, update, report, message):
        await report("⏳ Обновление и установка зависимостей...")
        try:
            await updater.install(update)
        except updater.InstallError as e:
            text = f"❌ <b>{utils.escape_html(e.stage)}</b>\n" + code_quote(e.output)
            if e.rolled_back:
                text += "\nВернул прежнюю версию, бот продолжает работать"
            else:
                text += "\n<b>Не удалось вернуть прежнюю версию</b>, не перезапускайте бот:\n" + code_quote(
                    e.rollback_output
                )
            await report(text)
            return
        if message is not None:
            await self.restart(message)
        else:
            await report("🔄 Обновлено, перезапуск...")
            await utils.restart(self.client)

    async def _channel(self, message, args):
        if args:
            if args[0] not in updater.CHANNELS:
                await utils.answer(
                    message, "❌ Каналы: <code>stable</code> (релизы) и <code>beta</code> (ветка master)"
                )
                return
            self.db.set("channel", args[0])
        channel = self._get_channel()
        about = "релизы (теги)" if channel == "stable" else "каждый коммит в master"
        await utils.answer(message, f"⚙️ Канал обновлений: <b>{channel}</b> — {about}")

    async def _notify(self, message, args):
        if args and args[0] in ("on", "off"):
            self.db.set("notify", args[0] == "on")
        state = "включены" if self.db.get("notify", True) else "выключены"
        await utils.answer(message, f"⚙️ Уведомления о новой версии раз в сутки {state}")

    @loop(interval=3600, wait_before=True)
    async def check_updates(self):
        """Раз в сутки проверяет обновления и пишет о новой версии в «Избранное»."""
        if (
            self.client is None
            or not self.db.get("notify", True)
            or updater.in_docker()
            or not updater.is_git_checkout()
            or time.time() - self.db.get("last_check", 0) < CHECK_EVERY
        ):
            return
        self.db.set("last_check", time.time())
        try:
            update = await updater.check(self._get_channel())
        except updater.UpdateError as e:
            logging.getLogger(__name__).info("Проверка обновлений не удалась: %s", e)
            return
        if update is None or self.db.get("notified") == update.sha:
            return
        self.db.set("notified", update.sha)
        prefix = utils.get_prefix(self.db.raw)
        text = self._changelog(update) + (
            f"\nУстановить: <code>{utils.escape_html(prefix)}update</code> · "
            f"отключить уведомления: <code>{utils.escape_html(prefix)}update notify off</code>"
        )
        await self.client.send_message("me", text, parse_mode="html")


def code_quote(output: str) -> str:
    return utils.quote(f"<code>{utils.escape_html(output[-3000:])}</code>", expandable=True)
