import asyncio
import io
import logging
import time

from uroboros import ConfigValue, Module, ModuleConfig, backup, command, loop, scan, utils, validators

log = logging.getLogger(__name__)
MAX_TRACKED = 100
SENT_KEY = "auto_sent"  # [[chat, message id], ...] of autobackups this bot sent, oldest first


def chat_value(value):
    """``me`` or a chat id (a number; groups and channels start with ``-100``)."""
    text = str(value).strip()
    if text.lower() in ("me", "self", "избранное"):
        return "me"
    if text.lstrip("-").isdigit():
        return int(text)
    raise validators.ValidationError("me / chat id")


chat_value.doc = "me / chat id"  # type: ignore[attr-defined]  # .cfg reads it as the value hint


class Backup(Module):
    """Back up and restore the database and modules"""

    strings = {
        "_cfg_doc_interval": "Auto backup every this many hours, 0 — off",
        "_cfg_doc_chat": "Where to send auto backups",
        "_cfg_doc_keep": "How many latest auto backups to keep in the chat, 0 — all",
        "auto_bad": "❌ <b>Didn't understand the auto backup setting</b>",
        "auto_daily": "⏱ <code>{prefix}backup auto 24</code> — once a day",
        "auto_keep": "🗂 <code>{prefix}backup auto 24 7</code> — and keep the latest 7",
        "auto_stop": "🛑 <code>{prefix}backup auto off</code> — turn off",
        "auto_off": "💾 <b>Auto backup is off</b>",
        "auto_on_hint": "once a day: <code>{prefix}backup auto 24</code>",
        "saved_messages": "Saved Messages",
        "chat": "chat <code>{chat}</code>",
        "auto_on": "💾 <b>Auto backup is on</b>",
        "every": "⏱ Every <code>{hours}</code> h",
        "where": "💬 Where: {where}",
        "keep_last": "🗂 Keep: the latest <code>{keep}</code>",
        "keep_all": "🗂 Keep: all",
        "own_chat_only": "⚠️ Contains the inline bot token: send it only to your own chat",
        "auto_hint": "chat — <code>{prefix}cfg backup chat</code> · turn off — <code>{prefix}backup auto off</code>",
        "contents": "🗄 Database and modules",
        "no_session": "🔒 No session and config.json",
        "token_inside": "⚠️ Contains the inline bot token: don't forward it",
        "restore_hint": "restore: reply to the file with <code>{prefix}restore</code>",
        "manual_title": "Uroboros backup",
        "auto_title": "Uroboros auto backup",
        "sent": "✅ <b>Backup sent</b> to Saved Messages",
        "reply_to_zip": "❌ <b>Reply to a backup zip file</b>",
        "too_big": "❌ <b>The archive is larger than 50 MB</b>",
        "restoring": "⏳ <b>Restoring the backup...</b>",
        "foreign_of": "account <code>{owner}</code>",
        "foreign_unknown": "an unknown account",
        "foreign": "👤 The backup is from {source}, not yours",
        "foreign_keeps": "🔐 Your access rights and inline bot stay as they are",
        "dangerous_title": "🚨 <b>Backup not restored: dangerous code in modules</b>",
        "foreign_title": "⚠️ <b>This is someone else's backup</b>",
        "force_hint": "if you trust the backup, reply to the file with <code>{command}</code>",
        "none": "none",
        "restored": "✅ <b>Backup restored</b>",
        "db_keys": "🗄 DB records: <code>{count}</code>",
        "modules": "📦 Modules: {names}",
        "notice": "⚠️ <b>Note</b>",
        "restarting": "🔄 <i>Restarting...</i>",
    }
    strings_ru = {
        "_cls_doc": "Бэкап и восстановление БД и модулей",
        "_cmd_doc_backup": (
            "[auto [часы | off] [сколько хранить]] — бэкап БД и модулей в «Избранное»; auto — по расписанию"
        ),
        "_cmd_doc_restore": (
            "[-f] (ответом на бэкап) — восстановить БД и модули и перезапуститься; -f — чужой бэкап или опасный код"
        ),
        "_cfg_doc_interval": "Автобэкап раз в столько часов, 0 — выключен",
        "_cfg_doc_chat": "Куда отправлять автобэкап",
        "_cfg_doc_keep": "Сколько последних автобэкапов хранить в чате, 0 — все",
        "auto_bad": "❌ <b>Не понял настройку автобэкапа</b>",
        "auto_daily": "⏱ <code>{prefix}backup auto 24</code> — раз в сутки",
        "auto_keep": "🗂 <code>{prefix}backup auto 24 7</code> — и хранить последние 7",
        "auto_stop": "🛑 <code>{prefix}backup auto off</code> — выключить",
        "auto_off": "💾 <b>Автобэкап выключен</b>",
        "auto_on_hint": "включить раз в сутки: <code>{prefix}backup auto 24</code>",
        "saved_messages": "«Избранное»",
        "chat": "чат <code>{chat}</code>",
        "auto_on": "💾 <b>Автобэкап включён</b>",
        "every": "⏱ Раз в <code>{hours}</code> ч",
        "where": "💬 Куда: {where}",
        "keep_last": "🗂 Хранить: последние <code>{keep}</code>",
        "keep_all": "🗂 Хранить: все",
        "own_chat_only": "⚠️ Внутри токен inline-бота: отправляйте только в свой чат",
        "auto_hint": "чат — <code>{prefix}cfg backup chat</code> · выключить — <code>{prefix}backup auto off</code>",
        "contents": "🗄 База данных и модули",
        "no_session": "🔒 Без сессии и config.json",
        "token_inside": "⚠️ Внутри токен inline-бота: не пересылайте",
        "restore_hint": "восстановить: ответьте на файл <code>{prefix}restore</code>",
        "manual_title": "Бэкап Uroboros",
        "auto_title": "Автобэкап Uroboros",
        "sent": "✅ <b>Бэкап отправлен</b> в «Избранное»",
        "reply_to_zip": "❌ <b>Ответьте на zip-файл бэкапа</b>",
        "too_big": "❌ <b>Архив больше 50 МБ</b>",
        "restoring": "⏳ <b>Восстанавливаю бэкап...</b>",
        "foreign_of": "аккаунта <code>{owner}</code>",
        "foreign_unknown": "неизвестного аккаунта",
        "foreign": "👤 Бэкап с {source}, а не с вашего",
        "foreign_keeps": "🔐 Права доступа и inline-бот останутся ваши",
        "dangerous_title": "🚨 <b>Бэкап не восстановлен: в модулях опасный код</b>",
        "foreign_title": "⚠️ <b>Это чужой бэкап</b>",
        "force_hint": "если доверяете бэкапу, ответьте на файл <code>{command}</code>",
        "none": "нет",
        "restored": "✅ <b>Бэкап восстановлен</b>",
        "db_keys": "🗄 Записей БД: <code>{count}</code>",
        "modules": "📦 Модули: {names}",
        "notice": "⚠️ <b>Обратите внимание</b>",
        "restarting": "🔄 <i>Перезапускаюсь...</i>",
    }

    def __init__(self):
        self.config = ModuleConfig(
            ConfigValue(
                "interval",
                0,
                "Auto backup every this many hours, 0 — off",
                validators.Integer(minimum=0, maximum=24 * 30),
            ),
            ConfigValue("chat", "me", "Where to send auto backups", chat_value),
            ConfigValue(
                "keep",
                5,
                "How many latest auto backups to keep in the chat, 0 — all",
                validators.Integer(minimum=0, maximum=100),
            ),
        )

    async def _send(self, chat, title_key):
        data = await asyncio.to_thread(backup.create, self.db.raw, self.loader.modules_dir, self.loader.security.me_id)
        file = io.BytesIO(data)
        file.name = backup.file_name()
        prefix = utils.get_prefix(self.db.raw)
        return await self.client.send_file(
            chat,
            file,
            caption=utils.card(
                f"💾 <b>{self.strings(title_key)}</b>",
                [self.strings("contents"), self.strings("no_session"), self.strings("token_inside")],
                hint=self.strings("restore_hint", prefix=prefix),
            ),
            parse_mode="html",
        )

    @command("backup", access="owner", emoji="💾")
    async def backup_cmd(self, message):
        """[auto [hours | off] [keep]] — back up the DB and modules to Saved Messages; auto — on a schedule"""
        args = utils.get_args(message)
        if args and args[0].lower() == "auto":
            await self._auto(message, args[1:])
            return
        await self._send("me", "manual_title")
        await utils.answer(message, self.strings("sent"))

    async def _auto(self, message, args):
        prefix = utils.get_prefix(self.db.raw)
        if args:
            try:
                hours = 0 if args[0].lower() == "off" else validators.Integer(minimum=1, maximum=24 * 30)(args[0])
                keep = validators.Integer(minimum=0, maximum=100)(args[1]) if len(args) > 1 else None
            except validators.ValidationError:
                await utils.answer(
                    message,
                    utils.card(
                        self.strings("auto_bad"),
                        [
                            self.strings("auto_daily", prefix=prefix),
                            self.strings("auto_keep", prefix=prefix),
                            self.strings("auto_stop", prefix=prefix),
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
            return utils.card(self.strings("auto_off"), hint=self.strings("auto_on_hint", prefix=prefix))
        where = self.strings("saved_messages") if chat == "me" else self.strings("chat", chat=chat)
        return utils.card(
            self.strings("auto_on"),
            [
                self.strings("every", hours=hours),
                self.strings("where", where=utils.Html(where)),
                self.strings("keep_last", keep=keep) if keep else self.strings("keep_all"),
                self.strings("own_chat_only"),
            ],
            hint=self.strings("auto_hint", prefix=prefix),
        )

    @loop(interval=600, wait_before=True)
    async def autobackup(self):
        """Auto backup on the schedule from the module settings."""
        hours = self.config["interval"]
        if not hours or self.client is None:
            return
        if time.time() - self.db.get("last_auto", 0) < hours * 3600:
            return
        self.db.set("last_auto", time.time())
        chat = self.config["chat"]
        try:
            sent = await self._send(chat, "auto_title")
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
        """[-f] (reply to a backup) — restore the DB and modules and restart; -f — foreign backup or dangerous code"""
        force = utils.get_args_raw(message).strip() == "-f"
        reply = await message.get_reply_message()
        if not reply or not reply.file:
            await utils.answer(message, self.strings("reply_to_zip"))
            return
        if reply.file.size and reply.file.size > backup.MAX_ARCHIVE:
            await utils.answer(message, self.strings("too_big"))
            return

        await utils.answer(message, self.strings("restoring"))
        data = await reply.download_media(bytes)
        # Разбор архива — в потоке, запись — здесь: соединение SQLite привязано к основному потоку.
        archive = await asyncio.to_thread(backup.parse, data)
        reports = {stem: scan.scan(source) for stem, source in archive.modules.items()}
        dangerous = {stem: report for stem, report in reports.items() if report.dangerous}
        foreign = archive.is_foreign(self.loader.security.me_id)
        if (dangerous or foreign) and not force:
            lines = []
            if foreign:
                source = (
                    self.strings("foreign_of", owner=archive.owner)
                    if archive.owner
                    else self.strings("foreign_unknown")
                )
                lines += [self.strings("foreign", source=utils.Html(source)), self.strings("foreign_keeps")]
            lines += [
                f"🧩 <b>{utils.escape_html(stem)}</b>: {scan.summary(r.dangerous)}" for stem, r in dangerous.items()
            ]
            title = self.strings("dangerous_title") if dangerous else self.strings("foreign_title")
            hint = self.strings("force_hint", command=utils.get_prefix(self.db.raw) + "restore -f")
            await utils.answer(message, utils.card(title, lines, hint=hint))
            return
        dump = backup.keep_account_settings(archive.dump, self.db.raw) if foreign else archive.dump
        restored = backup.apply(dump, archive.modules, self.db.raw, self.loader.modules_dir)
        names = ", ".join(restored.modules) or self.strings("none")
        notes = [
            f"🧩 <b>{utils.escape_html(stem)}</b>: {scan.summary(report.findings)}"
            for stem, report in reports.items()
            if report.findings
        ]
        await utils.answer(
            message,
            utils.card(
                self.strings("restored"),
                [self.strings("db_keys", count=restored.keys), self.strings("modules", names=names)],
            )
            + ("\n" + self.strings("notice") + "\n" + utils.quote("\n".join(notes)) if notes else "")
            + "\n"
            + self.strings("restarting"),
        )
        await self.loader.get_module("System").restart(message)
