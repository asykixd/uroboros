import asyncio
import io

from uroboros import Module, backup, command, utils


class Backup(Module):
    """Бэкап и восстановление БД и модулей"""

    @command("backup")
    async def backup_cmd(self, message):
        """— бэкап БД и модулей в «Избранное» (без сессии)"""
        data = await asyncio.to_thread(backup.create, self.db.raw, self.loader.modules_dir)
        file = io.BytesIO(data)
        file.name = backup.file_name()
        prefix = utils.get_prefix(self.db.raw)
        await self.client.send_file(
            "me",
            file,
            caption=f"📦 <b>Бэкап Uroboros</b>\nВосстановить: ответьте на файл <code>{prefix}restore</code>",
            parse_mode="html",
        )
        await utils.answer(message, "✅ Бэкап отправлен в «Избранное»")

    @command("restore")
    async def restore_cmd(self, message):
        """(ответом на бэкап) — восстановить БД и модули и перезапуститься"""
        reply = await message.get_reply_message()
        if not reply or not reply.file:
            await utils.answer(message, "❌ Ответьте на zip-файл бэкапа")
            return
        if reply.file.size and reply.file.size > backup.MAX_ARCHIVE:
            await utils.answer(message, "❌ Архив больше 50 МБ")
            return

        await utils.answer(message, "⏳ Восстановление...")
        data = await reply.download_media(bytes)
        # Разбор архива — в потоке, запись — здесь: соединение SQLite привязано к основному потоку.
        dump, modules = await asyncio.to_thread(backup.parse, data)
        restored = backup.apply(dump, modules, self.db.raw, self.loader.modules_dir)
        modules = ", ".join(restored.modules) or "нет"
        await utils.answer(
            message,
            "✅ <b>Восстановлено</b>\n"
            + utils.quote(f"Записей БД: <code>{restored.keys}</code>\nМодули: {utils.escape_html(modules)}"),
        )
        await self.loader.get_module("System").restart(message)
