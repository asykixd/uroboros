import asyncio
import io
import logging
import time

from uroboros import ConfigValue, Module, ModuleConfig, backup, command, loop, scan, utils, validators

log = logging.getLogger(__name__)
MAX_TRACKED = 100
SENT_KEY = "auto_sent"  # [[chat, message id], ...] of autobackups this bot sent, oldest first


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
            ConfigValue(
                "keep",
                5,
                "Сколько последних автобэкапов хранить в чате, 0 — все",
                validators.Integer(minimum=0, maximum=100),
            ),
        )

    async def _send(self, chat, title):
        data = await asyncio.to_thread(backup.create, self.db.raw, self.loader.modules_dir, self.loader.security.me_id)
        file = io.BytesIO(data)
        file.name = backup.file_name()
        prefix = utils.get_prefix(self.db.raw)
        return await self.client.send_file(
            chat,
            file,
            caption=utils.card(
                f"💾 <b>{title}</b>",
                ["🗄 База данных и модули", "🔒 Без сессии и config.json", "⚠️ Внутри токен inline-бота: не пересылайте"],
                hint=f"восстановить: ответьте на файл <code>{utils.escape_html(prefix)}restore</code>",
            ),
            parse_mode="html",
        )

    @command("backup", access="owner", emoji="💾")
    async def backup_cmd(self, message):
        """[auto [часы | off] [сколько хранить]] — бэкап БД и модулей в «Избранное»; auto — по расписанию"""
        args = utils.get_args(message)
        if args and args[0].lower() == "auto":
            await self._auto(message, args[1:])
            return
        await self._send("me", "Бэкап Uroboros")
        await utils.answer(message, "✅ <b>Бэкап отправлен</b> в «Избранное»")

    async def _auto(self, message, args):
        prefix = utils.escape_html(utils.get_prefix(self.db.raw))
        if args:
            try:
                hours = 0 if args[0].lower() == "off" else validators.Integer(minimum=1, maximum=24 * 30)(args[0])
                keep = validators.Integer(minimum=0, maximum=100)(args[1]) if len(args) > 1 else None
            except validators.ValidationError:
                await utils.answer(
                    message,
                    utils.card(
                        "❌ <b>Не понял настройку автобэкапа</b>",
                        [
                            f"⏱ <code>{prefix}backup auto 24</code> — раз в сутки",
                            f"🗂 <code>{prefix}backup auto 24 7</code> — и хранить последние 7",
                            f"🛑 <code>{prefix}backup auto off</code> — выключить",
                        ],
                    ),
                )
                return
            self.config["interval"] = hours
            if keep is not None:
                self.config["keep"] = keep
        await utils.answer(message, self._auto_card(prefix))

    def _auto_card(self, prefix):
        hours, chat, keep = self.config["interval"], self.config["chat"], self.config["keep"]
        if not hours:
            return utils.card(
                "💾 <b>Автобэкап выключен</b>",
                hint=f"включить раз в сутки: <code>{prefix}backup auto 24</code>",
            )
        where = "«Избранное»" if chat == "me" else f"чат <code>{chat}</code>"
        return utils.card(
            "💾 <b>Автобэкап включён</b>",
            [
                f"⏱ Раз в <code>{hours}</code> ч",
                f"💬 Куда: {where}",
                f"🗂 Хранить: {f'последние <code>{keep}</code>' if keep else 'все'}",
                "⚠️ Внутри токен inline-бота: отправляйте только в свой чат",
            ],
            hint=f"чат — <code>{prefix}cfg backup chat</code> · выключить — <code>{prefix}backup auto off</code>",
        )

    @loop(interval=600, wait_before=True)
    async def autobackup(self):
        """Автобэкап по расписанию из настроек модуля."""
        hours = self.config["interval"]
        if not hours or self.client is None:
            return
        if time.time() - self.db.get("last_auto", 0) < hours * 3600:
            return
        self.db.set("last_auto", time.time())
        chat = self.config["chat"]
        try:
            sent = await self._send(chat, "Автобэкап Uroboros")
        except Exception:
            log.exception("Автобэкап не отправлен в %s", chat)
            return
        if getattr(sent, "id", None) is not None:
            await self._rotate([*self.db.get(SENT_KEY, []), [chat, sent.id]])

    async def _rotate(self, sent):
        """Deletes autobackups beyond ``keep``: only ones this bot sent, so manual backups stay."""
        keep = self.config["keep"]
        old, sent = (sent[:-keep], sent[-keep:]) if keep and len(sent) > keep else ([], sent)
        self.db.set(SENT_KEY, sent[-MAX_TRACKED:])
        by_chat = {}
        for chat, message_id in old:
            by_chat.setdefault(chat, []).append(message_id)
        for chat, ids in by_chat.items():
            try:
                await self.client.delete_messages(chat, ids)
            except Exception:
                log.exception("Старые автобэкапы в %s не удалены", chat)

    @command("restore", access="owner", emoji="♻️")
    async def restore_cmd(self, message):
        """[-f] (ответом на бэкап) — восстановить БД и модули и перезапуститься; -f — чужой бэкап или опасный код"""
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
        archive = await asyncio.to_thread(backup.parse, data)
        reports = {stem: scan.scan(source) for stem, source in archive.modules.items()}
        dangerous = {stem: report for stem, report in reports.items() if report.dangerous}
        foreign = archive.is_foreign(self.loader.security.me_id)
        if (dangerous or foreign) and not force:
            lines = []
            if foreign:
                source = f"аккаунта <code>{archive.owner}</code>" if archive.owner else "неизвестного аккаунта"
                lines += [f"👤 Бэкап с {source}, а не с вашего", "🔐 Права доступа и inline-бот останутся ваши"]
            lines += [
                f"🧩 <b>{utils.escape_html(stem)}</b>: {scan.summary(r.dangerous)}" for stem, r in dangerous.items()
            ]
            title = (
                "🚨 <b>Бэкап не восстановлен: в модулях опасный код</b>" if dangerous else "⚠️ <b>Это чужой бэкап</b>"
            )
            hint = utils.escape_html(utils.get_prefix(self.db.raw) + "restore -f")
            await utils.answer(
                message,
                utils.card(title, lines, hint=f"если доверяете бэкапу, ответьте на файл <code>{hint}</code>"),
            )
            return
        dump = backup.keep_account_settings(archive.dump, self.db.raw) if foreign else archive.dump
        restored = backup.apply(dump, archive.modules, self.db.raw, self.loader.modules_dir)
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
