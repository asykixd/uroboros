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

CANCEL = {"text": "✖️ Отмена", "action": "close"}
CHECK_EVERY = 24 * 3600
DOCKER_UPDATE = "git pull &amp;&amp; docker compose up -d --build"
RELEASES_HINT = '📰 Что нового — в <a href="https://github.com/asykixd/uroboros/releases">релизах на GitHub</a>'
DEV_ARGS = {"on": "dev", "dev": "dev", "off": "master", "master": "master"}


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
            await self.client.edit_message(
                chat_id,
                message_id,
                f"✅ <b>Uroboros перезапущен</b> · за <code>{time.time() - started:.1f} с</code>",
                parse_mode="html",
            )

    @command("ping", access="support", emoji="📡")
    async def ping(self, message):
        """— задержка до Telegram"""
        start = time.perf_counter()
        await utils.answer(message, "📡 <b>Пинг</b> · ...")
        elapsed = (time.perf_counter() - start) * 1000
        await utils.answer(message, f"📡 <b>Пинг</b> · <code>{elapsed:.0f} мс</code>")

    @command("info", access="support", emoji="ℹ️")
    async def info(self, message):
        """— информация о юзерботе"""
        me = await self.client.get_me()
        prefix = utils.escape_html(utils.get_prefix(self.db.raw))
        lines = [
            f"👤 Аккаунт: <b>{utils.escape_html(me.first_name)}</b>",
            f"⏱ Аптайм: <code>{utils.format_duration(time.time() - utils.START_TIME)}</code>",
            f"📦 Модулей: <code>{len(self.loader.modules)}</code> · команд: <code>{len(self.loader.commands)}</code>",
            f"⌨️ Префикс: <code>{prefix}</code>",
        ]
        if updater.is_git_checkout() and not updater.in_docker():
            with contextlib.suppress(Exception):
                lines.append(f"🌿 Ветка: <code>{utils.escape_html(await updater.current_branch())}</code>")
        text = utils.card(f"🐍 <b>Uroboros</b> <code>{uroboros.__version__}</code>", lines)
        text += utils.quote(
            f"🐍 Python <code>{platform.python_version()}</code> · 📡 Telethon <code>{telethon.__version__}</code>\n"
            f"🖥 <code>{utils.escape_html(platform.platform())}</code>"
        )
        await utils.answer(message, text + f"\n💡 <i><code>{prefix}help</code> — все команды</i>")

    @command("logs", access="owner", emoji="📝")
    async def show_logs(self, message):
        """[уровень] — прислать логи файлом в «Избранное» (debug, info, warning, error, critical)"""
        arg = utils.get_args_raw(message).strip()
        level = logs.parse_level(arg) if arg else logging.NOTSET
        if level is None:
            await utils.answer(
                message,
                utils.card(
                    "❌ <b>Нет такого уровня логов</b>",
                    hint="уровни: <code>debug</code>, <code>info</code>, <code>warning</code>, "
                    "<code>error</code>, <code>critical</code>",
                ),
            )
            return
        if not logs.log_files():
            await utils.answer(message, "❌ <b>Логи в файл не пишутся</b>")
            return

        lines = await asyncio.to_thread(logs.read, level)
        level_name = logging.getLevelName(level) if level else "все"
        if not lines:
            await utils.answer(message, f"📝 В логах нет записей уровня <code>{level_name}</code>")
            return

        file = io.BytesIO("\n".join(lines).encode())
        file.name = "uroboros.log"
        # В логах бывают тексты сообщений и пути — в чужой чат их не шлём.
        await self.client.send_file(
            "me",
            file,
            caption=utils.card(
                "📝 <b>Логи Uroboros</b>",
                [f"🎚 Уровень: <code>{level_name}</code>", f"📄 Строк: <code>{len(lines)}</code>"],
            ),
            parse_mode="html",
        )
        await utils.answer(message, "✅ <b>Логи отправлены</b> в «Избранное»")

    @command("restart", access="owner", emoji="🔄")
    async def restart(self, message):
        """— перезапустить юзербот"""
        msg = await utils.answer(message, "🔄 <b>Перезапуск...</b>")
        self.db.set("restart", [msg.chat_id, msg.id, time.time()])
        await utils.restart(self.client)

    @command("update", access="owner", emoji="🆕")
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
            await utils.answer(
                message,
                utils.card(
                    "🐳 <b>Uroboros работает в Docker</b>", hint=f"обновляйтесь образом: <code>{DOCKER_UPDATE}</code>"
                ),
            )
            return
        if not updater.is_git_checkout() and not updater.is_pip_install():
            await utils.answer(message, "❌ <b>Uroboros установлен не из git и не через pip</b> — обновить его некому")
            return

        await utils.answer(message, "⏳ <b>Проверяю обновления...</b>")
        update = await self._check()
        if update is None:
            await utils.answer(
                message,
                f"✅ <b>Установлена последняя версия</b> <code>{uroboros.__version__}</code>"
                f" · канал {self._get_channel()}",
            )
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
        await utils.answer(message, text + f"\n💡 <i>Установить: <code>{utils.escape_html(prefix)}update -f</code></i>")

    def _get_channel(self):
        return self.db.get("channel", updater.DEFAULT_CHANNEL)

    @staticmethod
    def _changelog(update):
        shown = update.commits[: updater.MAX_CHANGELOG]
        lines = [
            f"▸ <code>{utils.escape_html(c.split(' ', 1)[0])}</code> {utils.escape_html(c.split(' ', 1)[-1])}"
            for c in shown
        ]
        if len(update.commits) > len(shown):
            lines.append("…")
        title = f"🆕 <b>Доступно обновление</b> · {utils.escape_html(update.label)}"
        if shown:
            count = f"{len(shown)}+" if len(update.commits) > len(shown) else str(len(shown))
            title += f" · изменений: {count}"
        return utils.card(title, lines or RELEASES_HINT, expandable=len(lines) > 10)

    async def _install_pressed(self, call, update):
        await call.edit("⏳ <b>Обновление...</b>", None)

        async def report(text):
            await call.edit(text, None)

        await self._install(update, report, None)

    async def _install(self, update, report, message):
        await report("⏳ <b>Обновление</b> · ставлю новую версию и зависимости...")
        action = (
            updater.install(update) if updater.is_git_checkout() else updater.install_pip(update, uroboros.__version__)
        )
        await self._apply(action, report, message, "🔄 <b>Обновлено</b> · перезапуск...")

    async def _check(self):
        """Обновление в текущем канале: из git, а если Uroboros поставлен через pip — с PyPI."""
        if updater.is_git_checkout():
            return await updater.check(self._get_channel())
        return await updater.check_pip(self._get_channel(), uroboros.__version__)

    async def _apply(self, action, report, message, done):
        """Ждёт ``action`` (обновление или смену ветки) и перезапускается; ошибку показывает через ``report``."""
        try:
            await action
        except updater.InstallError as e:
            text = f"❌ <b>{utils.escape_html(e.stage)}</b>\n" + code_quote(e.output)
            if e.rolled_back:
                text += "\n↩️ Вернул прежнюю версию, бот продолжает работать"
            else:
                text += "\n⚠️ <b>Не удалось вернуть прежнюю версию</b>, не перезапускайте бот:\n" + code_quote(
                    e.rollback_output
                )
            await report(text)
            return
        except updater.UpdateError as e:
            await report(f"❌ <b>{utils.escape_html(e)}</b>")
            return
        if message is not None:
            await self.restart(message)
        else:
            await report(done)
            await utils.restart(self.client)

    @command("dev", access="owner", emoji="🌿")
    async def dev(self, message):
        """[on | off] [-f] — ветка бота: on — сборка из dev (новое, до проверки), off — вернуться на master"""
        args = utils.get_args(message)
        force = "-f" in args
        args = [arg for arg in args if arg != "-f"]
        prefix = utils.escape_html(utils.get_prefix(self.db.raw))
        if updater.in_docker():
            await utils.answer(
                message,
                utils.card(
                    "🐳 <b>Uroboros работает в Docker</b>",
                    hint="ветку выбирают при сборке образа: <code>git switch dev</code>",
                ),
            )
            return
        if not updater.is_git_checkout():
            await utils.answer(message, "❌ <b>Ветки доступны только при установке из git</b>")
            return
        if not args:
            branch = await updater.current_branch()
            other, about = (
                ("off", "🧪 Сборка разработки: новое, но ещё не проверенное")
                if branch == "dev"
                else (
                    "on",
                    "🛡 Стабильная ветка",
                )
            )
            await utils.answer(
                message,
                utils.card(
                    f"🌿 <b>Ветка</b> <code>{utils.escape_html(branch)}</code>",
                    [f"🐍 Версия: <code>{uroboros.__version__}</code>", about],
                    hint=f"переключиться: <code>{prefix}dev {other}</code>",
                ),
            )
            return
        branch = DEV_ARGS.get(args[0].lower())
        if branch is None:
            await utils.answer(
                message,
                utils.card(
                    "❌ <b>Не понял, какая ветка</b>",
                    [
                        f"🧪 <code>{prefix}dev on</code> — сборка из dev",
                        f"🛡 <code>{prefix}dev off</code> — стабильная master",
                    ],
                ),
            )
            return

        await utils.answer(message, f"⏳ <b>Скачиваю ветку {branch}...</b>")
        target = await updater.prepare_switch(branch, uroboros.__version__)
        if force:
            await self._switch(target, lambda text: utils.answer(message, text), message)
            return
        text = self._switch_text(target)
        if self.inline.available:
            label = "🧪 Перейти на dev" if target.branch == "dev" else "🛡 Вернуться на master"
            buttons = [[{"text": label, "callback": self._switch_pressed, "args": (target,)}, CANCEL]]
            try:
                await self.inline.form(message, text, buttons)
                return
            except InlineError:
                pass
        await utils.answer(message, text + f"\n💡 <i>Переключить: <code>{prefix}dev {args[0]} -f</code></i>")

    def _switch_text(self, target):
        old, new = utils.escape_html(target.current_version), utils.escape_html(target.version)
        versions = f"🐍 Версия: <code>{old}</code> → <code>{new}</code>"
        if target.branch == "dev":
            prefix = utils.escape_html(utils.get_prefix(self.db.raw))
            title = "🧪 <b>Перейти на сборку из ветки dev?</b>"
            lines = [
                versions,
                "⚠️ Новые возможности до проверки: возможны ошибки",
                f"↩️ Вернуться — <code>{prefix}dev off</code>",
            ]
        else:
            title = "🛡 <b>Вернуться на стабильную ветку master?</b>"
            lines = [versions, "⚠️ Модули, которым нужна более новая версия, не загрузятся"]
        return utils.card(title, lines)

    async def _switch_pressed(self, call, target):
        async def report(text):
            await call.edit(text, None)

        await self._switch(target, report, None)

    async def _switch(self, target, report, message):
        if target.branch == "dev":
            self.db.set("channel", "beta")  # stable — теги master, в dev их нет
        await report(f"⏳ <b>Переключаюсь на {target.branch}</b> · ставлю зависимости...")
        await self._apply(updater.switch(target), report, message, f"🔄 <b>Ветка {target.branch}</b> · перезапуск...")

    async def _channel(self, message, args):
        if args:
            if args[0] not in updater.CHANNELS:
                await utils.answer(
                    message,
                    utils.card(
                        "❌ <b>Нет такого канала</b>",
                        ["🛡 <code>stable</code> — только релизы", "⚡ <code>beta</code> — каждый коммит в ветке"],
                    ),
                )
                return
            self.db.set("channel", args[0])
        channel = self._get_channel()
        about = "🛡 только релизы" if channel == "stable" else "⚡ каждый коммит в текущей ветке"
        await utils.answer(message, f"⚙️ <b>Канал обновлений</b> <code>{channel}</code> · {about}")

    async def _notify(self, message, args):
        if args and args[0] in ("on", "off"):
            self.db.set("notify", args[0] == "on")
        if self.db.get("notify", True):
            await utils.answer(message, "🔔 <b>Уведомления о новой версии включены</b> · раз в сутки")
        else:
            await utils.answer(message, "🔕 <b>Уведомления о новой версии выключены</b>")

    @loop(interval=3600, wait_before=True)
    async def check_updates(self):
        """Раз в сутки проверяет обновления и пишет о новой версии в «Избранное»."""
        if (
            self.client is None
            or not self.db.get("notify", True)
            or updater.in_docker()
            or not (updater.is_git_checkout() or updater.is_pip_install())
            or time.time() - self.db.get("last_check", 0) < CHECK_EVERY
        ):
            return
        self.db.set("last_check", time.time())
        try:
            update = await self._check()
        except updater.UpdateError as e:
            logging.getLogger(__name__).info("Проверка обновлений не удалась: %s", e)
            return
        if update is None or self.db.get("notified") == update.sha:
            return
        self.db.set("notified", update.sha)
        prefix = utils.get_prefix(self.db.raw)
        text = self._changelog(update) + (
            f"\n💡 <i>Установить: <code>{utils.escape_html(prefix)}update</code> · "
            f"не напоминать: <code>{utils.escape_html(prefix)}update notify off</code></i>"
        )
        await self.client.send_message("me", text, parse_mode="html")


def code_quote(output: str) -> str:
    return utils.quote(f"<code>{utils.escape_html(output[-3000:])}</code>", expandable=True)
