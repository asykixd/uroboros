import asyncio
import io
import logging
import time

from uroboros import ConfigValue, Module, ModuleConfig, backup, command, loop, scan, utils, validators

log = logging.getLogger(__name__)


def chat_value(value):
    """``me`` или id чата (число, для групп и каналов — с ``-100``)."""
    text = str(value).strip()
    if text.lower() in ("me", "self", "избранное"):
        return "me"
    if text.lstrip("-").isdigit():
        return int(text)
    raise validators.ValidationError("Нужно me или id чата")


chat_value.doc = "me или id чата"


class Backup(Module):
    """Бэкап и восстановление БД и модулей"""

    def __init__(self):
        self.config = ModuleConfig(
            ConfigValue(
                "interval",
                0,
                "Автобэкап раз в столько часов, 0 — выключен",
                validators.Integer(minimum=0, maximum=24 * 30),
            ),
            ConfigValue("chat", "me", "Куда отправлять автобэкап", chat_value),
        )

    async def _send(self, chat, title):
        data = await asyncio.to_thread(backup.create, self.db.raw, self.loader.modules_dir)
        file = io.BytesIO(data)
        file.name = backup.file_name()
        prefix = utils.get_prefix(self.db.raw)
        await self.client.send_file(
            chat,
            file,
            caption=utils.card(
                f"💾 <b>{title}</b>",
                ["🗄 База данных и модули", "🔒 Без сессии и ключей"],
                hint=f"восстановить: ответьте на файл <code>{utils.escape_html(prefix)}restore</code>",
            ),
            parse_mode="html",
        )

    @command("backup", access="owner", emoji="💾")
    async def backup_cmd(self, message):
        """— бэкап БД и модулей в «Избранное» (без сессии); автобэкап — .cfg backup"""
        await self._send("me", "Бэкап Uroboros")
        await utils.answer(message, "✅ <b>Бэкап отправлен</b> в «Избранное»")

    @loop(interval=600, wait_before=True)
    async def autobackup(self):
        """Автобэкап по расписанию из настроек модуля."""
        hours = self.config["interval"]
        if not hours or self.client is None:
            return
        if time.time() - self.db.get("last_auto", 0) < hours * 3600:
            return
        self.db.set("last_auto", time.time())
        try:
            await self._send(self.config["chat"], "Автобэкап Uroboros")
        except Exception:
            log.exception("Автобэкап не отправлен в %s", self.config["chat"])

    @command("restore", access="owner", emoji="♻️")
    async def restore_cmd(self, message):
        """[-f] (ответом на бэкап) — восстановить БД и модули и перезапуститься; -f — и с опасным кодом"""
        force = utils.get_args_raw(message).strip() == "-f"
        reply = await message.get_reply_message()
        if not reply or not reply.file:
            await utils.answer(message, "❌ <b>Ответьте на zip-файл бэкапа</b>")
            return
        if reply.file.size and reply.file.size > backup.MAX_ARCHIVE:
            await utils.answer(message, "❌ <b>Архив больше 50 МБ</b>")
            return

        await utils.answer(message, "⏳ <b>Восстанавливаю бэкап...</b>")
        data = await reply.download_media(bytes)
        # Разбор архива — в потоке, запись — здесь: соединение SQLite привязано к основному потоку.
        dump, modules = await asyncio.to_thread(backup.parse, data)
        reports = {stem: scan.scan(source) for stem, source in modules.items()}
        dangerous = {stem: report for stem, report in reports.items() if report.dangerous}
        if dangerous and not force:
            lines = [
                f"🧩 <b>{utils.escape_html(stem)}</b>: {scan.summary(r.dangerous)}" for stem, r in dangerous.items()
            ]
            hint = utils.escape_html(utils.get_prefix(self.db.raw) + "restore -f")
            await utils.answer(
                message,
                "🚨 <b>Бэкап не восстановлен: в модулях опасный код</b>\n"
                + utils.quote("\n".join(lines))
                + f"\n💡 <i>Если доверяете этим модулям, ответьте на файл <code>{hint}</code></i>",
            )
            return
        restored = backup.apply(dump, modules, self.db.raw, self.loader.modules_dir)
        names = ", ".join(restored.modules) or "нет"
        notes = [
            f"🧩 <b>{utils.escape_html(stem)}</b>: {scan.summary(report.findings)}"
            for stem, report in reports.items()
            if report.findings
        ]
        await utils.answer(
            message,
            utils.card(
                "✅ <b>Бэкап восстановлен</b>",
                [f"🗄 Записей БД: <code>{restored.keys}</code>", f"📦 Модули: {utils.escape_html(names)}"],
            )
            + ("\n⚠️ <b>Обратите внимание</b>\n" + utils.quote("\n".join(notes)) if notes else "")
            + "\n🔄 <i>Перезапускаюсь...</i>",
        )
        await self.loader.get_module("System").restart(message)
