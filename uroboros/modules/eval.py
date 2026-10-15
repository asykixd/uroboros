import ast
import asyncio
import contextlib
import inspect
import io
import traceback

import telethon

from uroboros import Module, command, utils


async def aeval(code, env):
    """Runs code with top-level await support. Returns the expression value or None."""
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
    """Run Python code and shell commands"""

    strings = {
        "no_code": "❌ <b>Which code to run?</b>",
        "code": "🐍 <b>Code</b>",
        "output": "📤 <b>Output</b>",
        "error": "❌ <b>Error</b>",
        "result": "✅ <b>Result</b>",
        "no_cmd": "❌ <b>Which command to run?</b>",
        "running": "⏳ <b>Running</b> <code>{cmd}</code>",
        "empty": "(empty)",
        "exit_code": "Exit code",
    }
    strings_ru = {
        "_cls_doc": "Выполнение Python-кода и shell-команд",
        "_cmd_doc_e": "<код> — выполнить Python-код (доступны client, message, reply, db, loader)",
        "_cmd_doc_t": "<команда> — выполнить shell-команду",
        "no_code": "❌ <b>Какой код выполнить?</b>",
        "code": "🐍 <b>Код</b>",
        "output": "📤 <b>Вывод</b>",
        "error": "❌ <b>Ошибка</b>",
        "result": "✅ <b>Результат</b>",
        "no_cmd": "❌ <b>Какую команду выполнить?</b>",
        "running": "⏳ <b>Выполняю</b> <code>{cmd}</code>",
        "empty": "(пусто)",
        "exit_code": "Код выхода",
    }

    @command("e", aliases=["eval"], access="owner", emoji="🐍")
    async def e(self, message):
        """<code> — run Python code (client, message, reply, db, loader are available)"""
        code = utils.get_args_raw(message)
        if not code:
            await utils.answer(message, utils.card(self.strings("no_code"), hint="<code>e 2 + 2</code>"))
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
            failed, output = False, "" if result is None else repr(result)
        except Exception:
            failed, output = True, traceback.format_exc(limit=-3)

        text = self.strings("code") + f'\n<pre><code class="language-python">{utils.escape_html(code)}</code></pre>'
        if stdout.getvalue():
            text += "\n" + self.strings("output") + f"\n<pre>{utils.escape_html(stdout.getvalue())}</pre>"
        if failed:
            text += "\n" + self.strings("error") + "\n"
            text += utils.quote(f"<code>{utils.escape_html(output)}</code>", expandable=True)
        elif output or not stdout.getvalue():
            text += "\n" + self.strings("result") + f"\n<pre>{utils.escape_html(output or 'None')}</pre>"
        await utils.answer(message, text)

    @command("t", aliases=["terminal"], access="owner", emoji="💻")
    async def t(self, message):
        """<command> — run a shell command"""
        cmd = utils.get_args_raw(message)
        if not cmd:
            await utils.answer(message, utils.card(self.strings("no_cmd"), hint="<code>t uptime</code>"))
            return
        await utils.answer(message, self.strings("running", cmd=cmd))
        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        output, _ = await proc.communicate()
        text = output.decode(errors="replace").strip() or self.strings("empty")
        status = "✅" if proc.returncode == 0 else "❌"
        await utils.answer(
            message,
            f"💻 <code>{utils.escape_html(cmd)}</code>\n<pre>{utils.escape_html(text)}</pre>\n"
            f"{status} {self.strings('exit_code')}: <code>{proc.returncode}</code>",
        )
