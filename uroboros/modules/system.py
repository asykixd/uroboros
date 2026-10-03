import asyncio
import contextlib
import io
import logging
import os
import platform
import sys
import time
from pathlib import Path

import telethon

import uroboros
from uroboros import Module, command, logs, utils

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

    @command("logs")
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
        code, old = await git("rev-parse", "HEAD")
        if code == 0:
            code, output = await git("pull", "--ff-only")
        else:
            output = old
        if code != 0:
            await utils.answer(message, "❌ <b>git pull завершился с ошибкой</b>\n" + code_quote(output))
            return
        _, new = await git("rev-parse", "HEAD")
        if new == old:
            await utils.answer(message, "✅ Установлена последняя версия")
            return

        # Новые зависимости ставятся до рестарта: если не встанут, бот после рестарта не запустится.
        await utils.answer(message, "⏳ Установка зависимостей...")
        code, output = await run_process(
            sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "-e", str(REPO_DIR)
        )
        stage = "Не удалось установить зависимости"
        if code == 0:
            code, output = await run_process(sys.executable, "-c", "import uroboros.main")
            stage = "Новая версия не запускается"
        if code != 0:
            rollback, rollback_output = await git("reset", "--keep", old)
            text = f"❌ <b>{stage}</b>\n" + code_quote(output)
            if rollback == 0:
                text += "\nВернул прежнюю версию, бот продолжает работать"
            else:
                text += "\n<b>Не удалось вернуть прежнюю версию</b>, не перезапускайте бот:\n" + code_quote(
                    rollback_output
                )
            await utils.answer(message, text)
            return
        await self.restart(message)


async def run_process(*args: str) -> tuple[int, str]:
    """Запускает процесс и возвращает код выхода и весь вывод."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},  # git не должен ждать логин в консоли
    )
    output, _ = await proc.communicate()
    return proc.returncode, output.decode(errors="replace").strip()


async def git(*args: str) -> tuple[int, str]:
    return await run_process("git", "-C", str(REPO_DIR), *args)


def code_quote(output: str) -> str:
    return utils.quote(f"<code>{utils.escape_html(output[-3000:])}</code>", expandable=True)
