import ast
import asyncio
import contextlib
import inspect
import io
import traceback

import telethon

from uroboros import Module, command, utils


async def aeval(code, env):
    """Выполняет код с поддержкой top-level await. Возвращает значение выражения или None."""
    flags = ast.PyCF_ALLOW_TOP_LEVEL_AWAIT
    try:
        compiled = compile(code, "<eval>", "eval", flags=flags)
    except SyntaxError:
        compiled = compile(code, "<eval>", "exec", flags=flags)
    result = eval(compiled, env)
    if inspect.isawaitable(result):
        result = await result
    return result


class Eval(Module):
    """Выполнение Python-кода и shell-команд"""

    @command("e", aliases=["eval"], access="owner", emoji="🐍")
    async def e(self, message):
        """<код> — выполнить Python-код (доступны client, message, reply, db, loader)"""
        code = utils.get_args_raw(message)
        if not code:
            await utils.answer(message, utils.card("❌ <b>Какой код выполнить?</b>", hint="<code>e 2 + 2</code>"))
            return

        reply = await message.get_reply_message()
        env = {
            "client": self.client,
            "message": message,
            "m": message,
            "reply": reply,
            "r": reply,
            "db": self.db.raw,
            "loader": self.loader,
            "utils": utils,
            "telethon": telethon,
            "asyncio": asyncio,
        }
        stdout = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout):
                result = await aeval(code, env)
            title, output = "Результат", "" if result is None else repr(result)
        except Exception:
            title, output = "Ошибка", traceback.format_exc(limit=-3)

        text = f'🐍 <b>Код</b>\n<pre><code class="language-python">{utils.escape_html(code)}</code></pre>'
        if stdout.getvalue():
            text += f"\n📤 <b>Вывод</b>\n<pre>{utils.escape_html(stdout.getvalue())}</pre>"
        if title == "Ошибка":
            text += "\n❌ <b>Ошибка</b>\n" + utils.quote(f"<code>{utils.escape_html(output)}</code>", expandable=True)
        elif output or not stdout.getvalue():
            text += f"\n✅ <b>Результат</b>\n<pre>{utils.escape_html(output or 'None')}</pre>"
        await utils.answer(message, text)

    @command("t", aliases=["terminal"], access="owner", emoji="💻")
    async def t(self, message):
        """<команда> — выполнить shell-команду"""
        cmd = utils.get_args_raw(message)
        if not cmd:
            await utils.answer(message, utils.card("❌ <b>Какую команду выполнить?</b>", hint="<code>t uptime</code>"))
            return
        await utils.answer(message, f"⏳ <b>Выполняю</b> <code>{utils.escape_html(cmd)}</code>")
        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        output, _ = await proc.communicate()
        text = output.decode(errors="replace").strip() or "(пусто)"
        status = "✅" if proc.returncode == 0 else "❌"
        await utils.answer(
            message,
            f"💻 <code>{utils.escape_html(cmd)}</code>\n<pre>{utils.escape_html(text)}</pre>\n"
            f"{status} Код выхода: <code>{proc.returncode}</code>",
        )
