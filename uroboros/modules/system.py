import asyncio
import contextlib
import platform
import sys
import time
from pathlib import Path

import telethon

import uroboros
from uroboros import Module, command, utils

REPO_DIR = Path(uroboros.__file__).resolve().parent.parent


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

    @command("ping")
    async def ping(self, message):
        """— задержка до Telegram"""
        start = time.perf_counter()
        await utils.answer(message, "⏱ <b>ping:</b> ...")
        elapsed = (time.perf_counter() - start) * 1000
        await utils.answer(message, f"⏱ <b>ping:</b> <code>{elapsed:.0f}ms</code>")

    @command("info")
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

    @command("restart")
    async def restart(self, message):
        """— перезапустить юзербот"""
        msg = await utils.answer(message, "🔄 Перезапуск...")
        self.db.set("restart", [msg.chat_id, msg.id, time.time()])
        await utils.restart(self.client)

    @command("update")
    async def update(self, message):
        """— обновиться из git и перезапуститься"""
        if not (REPO_DIR / ".git").exists():
            await utils.answer(message, "❌ Uroboros установлен не из git-репозитория")
            return
        await utils.answer(message, "⏳ Обновление...")
        proc = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            str(REPO_DIR),
            "pull",
            "--ff-only",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await proc.communicate()
        text = utils.escape_html(output.decode(errors="replace").strip())
        if proc.returncode != 0:
            await utils.answer(
                message,
                "❌ <b>git pull завершился с ошибкой</b>\n" + utils.quote(f"<code>{text}</code>", expandable=True),
            )
            return
        if "Already up to date" in text or "Уже актуально" in text:
            await utils.answer(message, "✅ Установлена последняя версия")
            return

        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "pip",
            "install",
            "-q",
            "--disable-pip-version-check",
            "-e",
            str(REPO_DIR),
        )
        await proc.wait()
        await self.restart(message)
