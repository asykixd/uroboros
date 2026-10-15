import asyncio
import contextlib
import io
import logging
import platform
import time

import telethon

import uroboros
from uroboros import Module, command, healthcheck, logs, loop, updater, utils
from uroboros.errors import InlineError

CHECK_EVERY = 24 * 3600
DOCKER_UPDATE = "git pull &amp;&amp; docker compose up -d --build"
RELEASES_URL = "https://github.com/asykixd/uroboros/releases"
DEV_ARGS = {"on": "dev", "dev": "dev", "off": "master", "master": "master"}

log = logging.getLogger(__name__)


class System(Module):
    """State, restart and updates"""

    strings = {
        "restarted": "✅ <b>Uroboros restarted</b> · in <code>{seconds} s</code>",
        "ping": "📡 <b>Ping</b> · {value}",
        "ms": "<code>{ms} ms</code>",
        "account": "👤 Account: <b>{name}</b>",
        "uptime": "⏱ Uptime: <code>{uptime}</code>",
        "modules": "📦 Modules: <code>{modules}</code> · commands: <code>{commands}</code>",
        "prefix": "⌨️ Prefix: <code>{prefix}</code>",
        "branch": "🌿 Branch: <code>{branch}</code>",
        "all_commands": "💡 <i><code>{prefix}help</code> — all commands</i>",
        "bad_level": "❌ <b>No such log level</b>",
        "levels_hint": (
            "levels: <code>debug</code>, <code>info</code>, <code>warning</code>, <code>error</code>, "
            "<code>critical</code>"
        ),
        "no_log_file": "❌ <b>Logs aren't written to a file</b>",
        "all_levels": "all",
        "no_records": "📝 No log records of level <code>{level}</code>",
        "logs_title": "📝 <b>Uroboros logs</b>",
        "log_level": "🎚 Level: <code>{level}</code>",
        "log_lines": "📄 Lines: <code>{count}</code>",
        "logs_sent": "✅ <b>Logs sent</b> to Saved Messages",
        "restarting": "🔄 <b>Restarting...</b>",
        "docker": "🐳 <b>Uroboros runs in Docker</b>",
        "docker_update": "update with the image: <code>{command}</code>",
        "no_updater": "❌ <b>Uroboros isn't installed from git or with pip</b> — nothing can update it",
        "checking": "⏳ <b>Checking for updates...</b>",
        "latest": "✅ <b>The latest version is installed</b> <code>{version}</code> · channel {channel}",
        "btn_update": "✅ Update",
        "cancel": "✖️ Cancel",
        "install_hint": "💡 <i>Install: <code>{prefix}update -f</code></i>",
        "available": "🆕 <b>Update available</b> · {label}",
        "changes": " · changes: {count}",
        "releases": '📰 What\'s new — in the <a href="{url}">GitHub releases</a>',
        "updating": "⏳ <b>Updating...</b>",
        "installing": "⏳ <b>Updating</b> · installing the new version and dependencies...",
        "updated": "🔄 <b>Updated</b> · restarting...",
        "rolled_back": "↩️ Rolled back to the previous version, the bot keeps running",
        "rollback_failed": "⚠️ <b>Couldn't restore the previous version</b>, don't restart the bot:",
        "rolled_back_title": "⚠️ <b>Update rolled back</b>",
        "failed_to_start": "🆕 Didn't start: <code>{target}</code>",
        "restored_version": "↩️ Restored version <code>{previous}</code>",
        "rollback_failed_title": "🚨 <b>The update didn't start and couldn't be rolled back</b>",
        "target_version": "🆕 Version: <code>{target}</code>",
        "restore_manually": "↩️ Restore <code>{previous}</code> manually",
        "docker_branch": "the branch is chosen when building the image: <code>git switch dev</code>",
        "no_branches": "❌ <b>Branches are only available for git or pip installs</b>",
        "dev_build": "🧪 Development build: new, but not tested yet",
        "stable_branch": "🛡 Stable branch",
        "branch_title": "🌿 <b>Branch</b> <code>{branch}</code>",
        "version": "🐍 Version: <code>{version}</code>",
        "switch_hint": "switch: <code>{prefix}dev {other}</code>",
        "unknown_branch": "❌ <b>Which branch?</b>",
        "dev_on": "🧪 <code>{prefix}dev on</code> — dev build",
        "dev_off": "🛡 <code>{prefix}dev off</code> — stable master",
        "downloading_branch": "⏳ <b>Downloading branch {branch}...</b>",
        "btn_to_dev": "🧪 Switch to dev",
        "btn_to_master": "🛡 Back to master",
        "switch_force_hint": "💡 <i>Switch: <code>{prefix}dev {arg} -f</code></i>",
        "versions": "🐍 Version: <code>{old}</code> → <code>{new}</code>",
        "to_dev": "🧪 <b>Switch to the dev branch build?</b>",
        "dev_warning": "⚠️ New features before testing: bugs are possible",
        "dev_back": "↩️ Go back — <code>{prefix}dev off</code>",
        "to_master": "🛡 <b>Go back to the stable master branch?</b>",
        "master_warning": "⚠️ Modules that need a newer version won't load",
        "switching": "⏳ <b>Switching to {branch}</b> · installing dependencies...",
        "switched": "🔄 <b>Branch {branch}</b> · restarting...",
        "no_channel": "❌ <b>No such channel</b>",
        "stable_about": "🛡 <code>stable</code> — releases only",
        "beta_about": "⚡ <code>beta</code> — every commit on the branch",
        "stable_short": "🛡 releases only",
        "beta_short": "⚡ every commit on the current branch",
        "channel": "⚙️ <b>Update channel</b> <code>{channel}</code> · {about}",
        "notify_on": "🔔 <b>New version notices are on</b> · once a day",
        "notify_off": "🔕 <b>New version notices are off</b>",
        "notify_hint": (
            "💡 <i>Install: <code>{prefix}update</code> · don't remind: <code>{prefix}update notify off</code></i>"
        ),
    }
    strings_ru = {
        "_cls_doc": "Состояние, перезапуск и обновление",
        "_cmd_doc_ping": "— задержка до Telegram",
        "_cmd_doc_info": "— информация о юзерботе",
        "_cmd_doc_logs": "[уровень] — прислать логи файлом в «Избранное» (debug, info, warning, error, critical)",
        "_cmd_doc_restart": "— перезапустить юзербот",
        "_cmd_doc_update": "[-f | channel stable|beta | notify on|off] — обновиться: список изменений и подтверждение",
        "_cmd_doc_dev": (
            "[on | off] [-f] — ветка бота: on — сборка из dev (новое, до проверки), off — вернуться на master"
        ),
        "restarted": "✅ <b>Uroboros перезапущен</b> · за <code>{seconds} с</code>",
        "ping": "📡 <b>Пинг</b> · {value}",
        "ms": "<code>{ms} мс</code>",
        "account": "👤 Аккаунт: <b>{name}</b>",
        "uptime": "⏱ Аптайм: <code>{uptime}</code>",
        "modules": "📦 Модулей: <code>{modules}</code> · команд: <code>{commands}</code>",
        "prefix": "⌨️ Префикс: <code>{prefix}</code>",
        "branch": "🌿 Ветка: <code>{branch}</code>",
        "all_commands": "💡 <i><code>{prefix}help</code> — все команды</i>",
        "bad_level": "❌ <b>Нет такого уровня логов</b>",
        "levels_hint": (
            "уровни: <code>debug</code>, <code>info</code>, <code>warning</code>, <code>error</code>, "
            "<code>critical</code>"
        ),
        "no_log_file": "❌ <b>Логи в файл не пишутся</b>",
        "all_levels": "все",
        "no_records": "📝 В логах нет записей уровня <code>{level}</code>",
        "logs_title": "📝 <b>Логи Uroboros</b>",
        "log_level": "🎚 Уровень: <code>{level}</code>",
        "log_lines": "📄 Строк: <code>{count}</code>",
        "logs_sent": "✅ <b>Логи отправлены</b> в «Избранное»",
        "restarting": "🔄 <b>Перезапуск...</b>",
        "docker": "🐳 <b>Uroboros работает в Docker</b>",
        "docker_update": "обновляйтесь образом: <code>{command}</code>",
        "no_updater": "❌ <b>Uroboros установлен не из git и не через pip</b> — обновить его некому",
        "checking": "⏳ <b>Проверяю обновления...</b>",
        "latest": "✅ <b>Установлена последняя версия</b> <code>{version}</code> · канал {channel}",
        "btn_update": "✅ Обновить",
        "cancel": "✖️ Отмена",
        "install_hint": "💡 <i>Установить: <code>{prefix}update -f</code></i>",
        "available": "🆕 <b>Доступно обновление</b> · {label}",
        "changes": " · изменений: {count}",
        "releases": '📰 Что нового — в <a href="{url}">релизах на GitHub</a>',
        "updating": "⏳ <b>Обновление...</b>",
        "installing": "⏳ <b>Обновление</b> · ставлю новую версию и зависимости...",
        "updated": "🔄 <b>Обновлено</b> · перезапуск...",
        "rolled_back": "↩️ Вернул прежнюю версию, бот продолжает работать",
        "rollback_failed": "⚠️ <b>Не удалось вернуть прежнюю версию</b>, не перезапускайте бот:",
        "rolled_back_title": "⚠️ <b>Обновление откачено</b>",
        "failed_to_start": "🆕 Не запустилось: <code>{target}</code>",
        "restored_version": "↩️ Вернул версию <code>{previous}</code>",
        "rollback_failed_title": "🚨 <b>Обновление не запустилось, откатить не удалось</b>",
        "target_version": "🆕 Версия: <code>{target}</code>",
        "restore_manually": "↩️ Верните <code>{previous}</code> вручную",
        "docker_branch": "ветку выбирают при сборке образа: <code>git switch dev</code>",
        "no_branches": "❌ <b>Ветки доступны только при установке из git или через pip</b>",
        "dev_build": "🧪 Сборка разработки: новое, но ещё не проверенное",
        "stable_branch": "🛡 Стабильная ветка",
        "branch_title": "🌿 <b>Ветка</b> <code>{branch}</code>",
        "version": "🐍 Версия: <code>{version}</code>",
        "switch_hint": "переключиться: <code>{prefix}dev {other}</code>",
        "unknown_branch": "❌ <b>Не понял, какая ветка</b>",
        "dev_on": "🧪 <code>{prefix}dev on</code> — сборка из dev",
        "dev_off": "🛡 <code>{prefix}dev off</code> — стабильная master",
        "downloading_branch": "⏳ <b>Скачиваю ветку {branch}...</b>",
        "btn_to_dev": "🧪 Перейти на dev",
        "btn_to_master": "🛡 Вернуться на master",
        "switch_force_hint": "💡 <i>Переключить: <code>{prefix}dev {arg} -f</code></i>",
        "versions": "🐍 Версия: <code>{old}</code> → <code>{new}</code>",
        "to_dev": "🧪 <b>Перейти на сборку из ветки dev?</b>",
        "dev_warning": "⚠️ Новые возможности до проверки: возможны ошибки",
        "dev_back": "↩️ Вернуться — <code>{prefix}dev off</code>",
        "to_master": "🛡 <b>Вернуться на стабильную ветку master?</b>",
        "master_warning": "⚠️ Модули, которым нужна более новая версия, не загрузятся",
        "switching": "⏳ <b>Переключаюсь на {branch}</b> · ставлю зависимости...",
        "switched": "🔄 <b>Ветка {branch}</b> · перезапуск...",
        "no_channel": "❌ <b>Нет такого канала</b>",
        "stable_about": "🛡 <code>stable</code> — только релизы",
        "beta_about": "⚡ <code>beta</code> — каждый коммит в ветке",
        "stable_short": "🛡 только релизы",
        "beta_short": "⚡ каждый коммит в текущей ветке",
        "channel": "⚙️ <b>Канал обновлений</b> <code>{channel}</code> · {about}",
        "notify_on": "🔔 <b>Уведомления о новой версии включены</b> · раз в сутки",
        "notify_off": "🔕 <b>Уведомления о новой версии выключены</b>",
        "notify_hint": (
            "💡 <i>Установить: <code>{prefix}update</code> · не напоминать: <code>{prefix}update notify off</code></i>"
        ),
    }

    @property
    def _cancel(self):
        return {"text": self.strings("cancel"), "action": "close"}

    def _prefix(self):
        return utils.get_prefix(self.db.raw)

    @property
    def _data_dir(self):
        return self.loader.modules_dir.parent  # modules/ lives in the data dir (Config.modules_dir)

    async def on_load(self):
        await self._report_rollback()
        # A restart started by a command reports in the same message.
        pending = self.db.get("restart")
        if not pending or self.client is None:
            return
        self.db.delete("restart")
        chat_id, message_id, started = pending
        with contextlib.suppress(Exception):
            await self.client.edit_message(
                chat_id,
                message_id,
                self.strings("restarted", seconds=f"{time.time() - started:.1f}"),
                parse_mode="html",
            )

    async def _report_rollback(self):
        """The last update didn't start and was rolled back (``healthcheck``): report it to Saved Messages."""
        if self.client is None:
            return
        notice = healthcheck.take_notice(self._data_dir)
        if notice is None:
            return
        previous = notice.get("previous", "?")
        target = notice.get("target", "?")
        if notice.get("ok"):
            title = self.strings("rolled_back_title")
            lines = [
                self.strings("failed_to_start", target=target),
                self.strings("restored_version", previous=previous),
            ]
        else:
            title = self.strings("rollback_failed_title")
            lines = [self.strings("target_version", target=target), self.strings("restore_manually", previous=previous)]
        text = utils.card(title, lines)
        text += "\n" + code_quote(notice.get("reason", "") + "\n" + notice.get("output", ""))
        try:
            await self.client.send_message("me", text, parse_mode="html")
        except Exception:
            log.exception("Не удалось сообщить об откате обновления")

    @command("ping", access="support", emoji="📡")
    async def ping(self, message):
        """— latency to Telegram"""
        start = time.perf_counter()
        await utils.answer(message, self.strings("ping", value="..."))
        elapsed = (time.perf_counter() - start) * 1000
        await utils.answer(message, self.strings("ping", value=utils.Html(self.strings("ms", ms=f"{elapsed:.0f}"))))

    @command("info", access="support", emoji="ℹ️")
    async def info(self, message):
        """— about this userbot"""
        me = await self.client.get_me()
        prefix = self._prefix()
        lines = [
            self.strings("account", name=me.first_name),
            self.strings("uptime", uptime=utils.format_duration(time.time() - utils.START_TIME)),
            self.strings("modules", modules=len(self.loader.modules), commands=len(self.loader.commands)),
            self.strings("prefix", prefix=prefix),
        ]
        if (updater.is_git_checkout() or updater.is_pip_install()) and not updater.in_docker():
            with contextlib.suppress(Exception):
                lines.append(self.strings("branch", branch=await self._branch()))
        text = utils.card(f"🐍 <b>Uroboros</b> <code>{uroboros.__version__}</code>", lines)
        text += utils.quote(
            f"🐍 Python <code>{platform.python_version()}</code> · 📡 Telethon <code>{telethon.__version__}</code>\n"
            f"🖥 <code>{utils.escape_html(platform.platform())}</code>"
        )
        await utils.answer(message, text + "\n" + self.strings("all_commands", prefix=prefix))

    @command("logs", access="owner", emoji="📝")
    async def show_logs(self, message):
        """[level] — send logs as a file to Saved Messages (debug, info, warning, error, critical)"""
        arg = utils.get_args_raw(message).strip()
        level = logs.parse_level(arg) if arg else logging.NOTSET
        if level is None:
            await utils.answer(message, utils.card(self.strings("bad_level"), hint=self.strings("levels_hint")))
            return
        if not logs.log_files():
            await utils.answer(message, self.strings("no_log_file"))
            return

        lines = await asyncio.to_thread(logs.read, level)
        level_name = logging.getLevelName(level) if level else self.strings("all_levels")
        if not lines:
            await utils.answer(message, self.strings("no_records", level=level_name))
            return

        file = io.BytesIO("\n".join(lines).encode())
        file.name = "uroboros.log"
        # Logs contain message texts and paths: never send them to someone else's chat.
        await self.client.send_file(
            "me",
            file,
            caption=utils.card(
                self.strings("logs_title"),
                [self.strings("log_level", level=level_name), self.strings("log_lines", count=len(lines))],
            ),
            parse_mode="html",
        )
        await utils.answer(message, self.strings("logs_sent"))

    @command("restart", access="owner", emoji="🔄")
    async def restart(self, message):
        """— restart the userbot"""
        msg = await utils.answer(message, self.strings("restarting"))
        self.db.set("restart", [msg.chat_id, msg.id, time.time()])
        await utils.restart(self.client)

    @command("update", access="owner", emoji="🆕")
    async def update(self, message):
        """[-f | channel stable|beta | notify on|off] — update: changelog first, then confirmation"""
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
                    self.strings("docker"),
                    hint=self.strings("docker_update", command=utils.Html(DOCKER_UPDATE)),
                ),
            )
            return
        if not updater.is_git_checkout() and not updater.is_pip_install():
            await utils.answer(message, self.strings("no_updater"))
            return

        await utils.answer(message, self.strings("checking"))
        update = await self._check()
        if update is None:
            await utils.answer(
                message, self.strings("latest", version=uroboros.__version__, channel=self._get_channel())
            )
            return
        if args and args[0] == "-f":
            await self._install(update, lambda text: utils.answer(message, text), message)
            return

        text = self._changelog(update)
        if self.inline.available:
            buttons = [
                [
                    {"text": self.strings("btn_update"), "callback": self._install_pressed, "args": (update,)},
                    self._cancel,
                ]
            ]
            try:
                await self.inline.form(message, text, buttons)
                return
            except InlineError:
                pass  # e.g. inline bots are banned in this chat
        await utils.answer(message, text + "\n" + self.strings("install_hint", prefix=self._prefix()))

    def _get_channel(self):
        return self.db.get("channel", updater.DEFAULT_CHANNEL)

    def _changelog(self, update):
        shown = update.commits[: updater.MAX_CHANGELOG]
        lines = [
            f"▸ <code>{utils.escape_html(c.split(' ', 1)[0])}</code> {utils.escape_html(c.split(' ', 1)[-1])}"
            for c in shown
        ]
        if len(update.commits) > len(shown):
            lines.append("…")
        title = self.strings("available", label=update.label)
        if shown:
            count = f"{len(shown)}+" if len(update.commits) > len(shown) else str(len(shown))
            title += self.strings("changes", count=count)
        body = lines or self.strings("releases", url=RELEASES_URL)
        return utils.card(title, body, expandable=len(lines) > 10)

    async def _install_pressed(self, call, update):
        await call.edit(self.strings("updating"), None)

        async def report(text):
            await call.edit(text, None)

        await self._install(update, report, None)

    async def _install(self, update, report, message):
        await report(self.strings("installing"))
        action = (
            updater.install(update) if updater.is_git_checkout() else updater.install_pip(update, uroboros.__version__)
        )
        await self._apply(action, report, message, self.strings("updated"), update.label)

    async def _check(self):
        """An update in the current channel: from git, or from PyPI for pip installs."""
        if updater.is_git_checkout():
            return await updater.check(self._get_channel())
        return await updater.check_pip(self._get_channel(), uroboros.__version__)

    async def _apply(self, action, report, message, done, label):
        """Waits for ``action`` (update or branch switch) and restarts; shows errors through ``report``.

        Before restarting it records how to return to the previous version: if the new one doesn't get ready,
        ``main`` rolls it back by itself.
        """
        try:
            rollback = await action
        except updater.InstallError as e:
            text = f"❌ <b>{utils.escape_html(e.stage)}</b>\n" + code_quote(e.output)
            if e.rolled_back:
                text += "\n" + self.strings("rolled_back")
            else:
                text += "\n" + self.strings("rollback_failed") + "\n" + code_quote(e.rollback_output)
            await report(text)
            return
        except updater.UpdateError as e:
            await report(f"❌ <b>{utils.escape_html(e)}</b>")
            return
        try:
            healthcheck.arm(self._data_dir, rollback, uroboros.__version__, label)
        except (OSError, ValueError):
            log.exception("Не удалось подготовить откат: новая версия будет без проверки запуска")
        if message is not None:
            await self.restart(message)
        else:
            await report(done)
            await utils.restart(self.client)

    @command("dev", access="owner", emoji="🌿")
    async def dev(self, message):
        """[on | off] [-f] — bot branch: on — dev build (new, before testing), off — back to master"""
        args = utils.get_args(message)
        force = "-f" in args
        args = [arg for arg in args if arg != "-f"]
        prefix = self._prefix()
        if updater.in_docker():
            await utils.answer(message, utils.card(self.strings("docker"), hint=self.strings("docker_branch")))
            return
        if not updater.is_git_checkout() and not updater.is_pip_install():
            await utils.answer(message, self.strings("no_branches"))
            return
        if not args:
            branch = await self._branch()
            other, about = (
                ("off", self.strings("dev_build")) if branch == "dev" else ("on", self.strings("stable_branch"))
            )
            await utils.answer(
                message,
                utils.card(
                    self.strings("branch_title", branch=branch),
                    [self.strings("version", version=uroboros.__version__), about],
                    hint=self.strings("switch_hint", prefix=prefix, other=other),
                ),
            )
            return
        branch = DEV_ARGS.get(args[0].lower())
        if branch is None:
            await utils.answer(
                message,
                utils.card(
                    self.strings("unknown_branch"),
                    [self.strings("dev_on", prefix=prefix), self.strings("dev_off", prefix=prefix)],
                ),
            )
            return

        await utils.answer(message, self.strings("downloading_branch", branch=branch))
        if updater.is_git_checkout():
            target = await updater.prepare_switch(branch, uroboros.__version__)
        else:
            target = await updater.prepare_switch_pip(branch, uroboros.__version__)
        if force:
            await self._switch(target, lambda text: utils.answer(message, text), message)
            return
        text = self._switch_text(target)
        if self.inline.available:
            label = self.strings("btn_to_dev") if target.branch == "dev" else self.strings("btn_to_master")
            buttons = [[{"text": label, "callback": self._switch_pressed, "args": (target,)}, self._cancel]]
            try:
                await self.inline.form(message, text, buttons)
                return
            except InlineError:
                pass
        await utils.answer(message, text + "\n" + self.strings("switch_force_hint", prefix=prefix, arg=args[0]))

    @staticmethod
    async def _branch():
        return await updater.current_branch() if updater.is_git_checkout() else updater.pip_branch()

    def _switch_text(self, target):
        versions = self.strings("versions", old=target.current_version, new=target.version)
        if target.branch == "dev":
            title = self.strings("to_dev")
            lines = [versions, self.strings("dev_warning"), self.strings("dev_back", prefix=self._prefix())]
        else:
            title = self.strings("to_master")
            lines = [versions, self.strings("master_warning")]
        return utils.card(title, lines)

    async def _switch_pressed(self, call, target):
        async def report(text):
            await call.edit(text, None)

        await self._switch(target, report, None)

    async def _switch(self, target, report, message):
        async def action():
            rollback = await (updater.switch(target) if updater.is_git_checkout() else updater.switch_pip(target))
            if target.branch == "dev":
                self.db.set("channel", "beta")  # stable means master tags; dev has none
            return rollback

        await report(self.strings("switching", branch=target.branch))
        await self._apply(
            action(),
            report,
            message,
            self.strings("switched", branch=target.branch),
            f"{target.branch} {target.version}",
        )

    async def _channel(self, message, args):
        if args:
            if args[0] not in updater.CHANNELS:
                await utils.answer(
                    message,
                    utils.card(self.strings("no_channel"), [self.strings("stable_about"), self.strings("beta_about")]),
                )
                return
            self.db.set("channel", args[0])
        channel = self._get_channel()
        about = self.strings("stable_short") if channel == "stable" else self.strings("beta_short")
        await utils.answer(message, self.strings("channel", channel=channel, about=about))

    async def _notify(self, message, args):
        if args and args[0] in ("on", "off"):
            self.db.set("notify", args[0] == "on")
        key = "notify_on" if self.db.get("notify", True) else "notify_off"
        await utils.answer(message, self.strings(key))

    @loop(interval=3600, wait_before=True)
    async def check_updates(self):
        """Checks for updates once a day and reports a new version to Saved Messages."""
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
        text = self._changelog(update) + "\n" + self.strings("notify_hint", prefix=self._prefix())
        await self.client.send_message("me", text, parse_mode="html")


def code_quote(output: str) -> str:
    return utils.quote(f"<code>{utils.escape_html(output[-3000:])}</code>", expandable=True)
