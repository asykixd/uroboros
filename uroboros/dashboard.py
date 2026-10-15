"""Read-only web dashboard after login: modules, inline bot state, recent logs.

Off by default (``--dashboard`` or ``UROBOROS_DASHBOARD=1``), listens on ``127.0.0.1`` unless told otherwise, and
every request must carry the random token from the link printed to the console. It only reads loader state and the
log file: nothing here touches the session, ``config.json`` or the database, and every value is HTML-escaped.
"""

from __future__ import annotations

import asyncio
import hmac
import html
import logging
import secrets
import time
from typing import TYPE_CHECKING

from aiohttp import web as aioweb

from . import __version__, logs, utils
from .web import LOGO, STYLE

if TYPE_CHECKING:
    from .loader import Loader

log = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8081
LOG_LINES = 200
HEADERS = {
    "Cache-Control": "no-store",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    # No scripts at all; the page is static HTML with inline styles.
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:; form-action 'none'",
}
EXTRA_STYLE = """
main { max-width: 900px; }
body { align-items: flex-start; }
h2 { font-size: 16px; margin: 22px 0 8px; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--border); vertical-align: top; }
th { color: var(--muted); font-weight: 600; }
td.wrap { word-break: break-all; }
pre { background: var(--field); border: 1px solid var(--border); border-radius: 12px; padding: 12px; font-size: 12px;
      overflow-x: auto; max-height: 480px; white-space: pre-wrap; word-break: break-word; }
.bad { color: var(--error); }
.tag { font-size: 12px; color: var(--muted); }
"""
DENIED = (
    '<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Uroboros</title></head>'
    "<body><p>Нет доступа: откройте ссылку из консоли целиком.</p></body></html>"
)


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _modules(loader: Loader) -> str:
    trusted = loader.guard.trusted()
    limiter = loader.ratelimit
    rows = []
    modules = sorted(loader.modules.values(), key=lambda m: (not m.is_builtin, m.name.lower()))
    for module in modules:
        commands = ", ".join(cmd.name for cmd in loader.module_commands(module)) or "—"
        notes = []
        if module.is_builtin:
            notes.append("встроенный")
        elif module._stem in trusted:
            notes.append('<span class="bad">без защиты</span>')
        if limiter.frozen_for(module.name):
            notes.append('<span class="bad">заморожен</span>')
        origin = "" if module.is_builtin else _e(module._origin)
        rows.append(
            f"<tr><td><b>{_e(module.name)}</b><br><span class='tag'>{', '.join(notes)}</span></td>"
            f"<td>{_e(commands)}</td><td class='wrap'>{origin}</td></tr>"
        )
    table = (
        "<table><tr><th>Модуль</th><th>Команды</th><th>Источник</th></tr>" + "".join(rows) + "</table>"
        if rows
        else "<p>Модули не загружены.</p>"
    )
    problems = [
        f"<tr><td><b>{_e(stem)}</b></td><td class='bad'>{_e(reason)}</td></tr>"
        for stem, reason in sorted(loader.failures.items())
    ]
    problems += [
        f"<tr><td><b>{_e(stem)}</b></td><td>файл изменён не через Uroboros</td></tr>"
        for stem in sorted(loader.tampered)
        if stem not in loader.failures
    ]
    if problems:
        table += "<h2>⚠️ Проблемы</h2><table>" + "".join(problems) + "</table>"
    return table


def _inline(loader: Loader) -> str:
    manager = loader.inline
    if manager is None:
        return "<p>Inline-бот не подключён.</p>"
    if manager.ready:
        return f"<p>✅ Работает: @{_e(manager.bot_username)}</p>"
    return f"<p class='bad'>❌ Не запущен: {_e(manager.error or 'причина в логах')}</p>"


async def _logs() -> str:
    if not logs.log_files():
        return "<p>Логи в файл не пишутся.</p>"
    lines = await asyncio.to_thread(logs.read)
    return f"<pre>{_e(chr(10).join(lines[-LOG_LINES:]))}</pre>"


async def render(loader: Loader) -> str:
    uptime = utils.format_duration(time.time() - utils.START_TIME)
    content = (
        f"<h1>Состояние</h1><p>Uroboros {_e(__version__)} · аптайм {_e(uptime)} · модулей {len(loader.modules)}, "
        f"команд {len(loader.commands)}</p>"
        f"<h2>🤖 Inline-бот</h2>{_inline(loader)}"
        f"<h2>📦 Модули</h2>{_modules(loader)}"
        f"<h2>📝 Последние записи лога</h2>{await _logs()}"
    )
    return (
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Uroboros — состояние</title>"
        f"<style>{STYLE}{EXTRA_STYLE}</style></head><body><main>"
        f'<header class="brand">{LOGO}<div><b>Uroboros</b><span>панель состояния, только чтение</span></div></header>'
        f"{content}<footer>🔒 Только чтение · обновите страницу, чтобы увидеть новые данные</footer>"
        "</main></body></html>"
    )


def make_app(loader: Loader, token: str) -> aioweb.Application:
    async def show(request: aioweb.Request) -> aioweb.Response:
        given = request.query.get("token")
        if given is None or not hmac.compare_digest(given, token):
            return aioweb.Response(text=DENIED, status=403, content_type="text/html", headers=HEADERS)
        return aioweb.Response(text=await render(loader), content_type="text/html", headers=HEADERS)

    app = aioweb.Application()
    app.router.add_get("/", show)
    return app


async def start(loader: Loader, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> aioweb.AppRunner | None:
    """Starts the dashboard and prints its link; None if the port can't be opened (the bot keeps running)."""
    token = secrets.token_urlsafe(24)
    runner = aioweb.AppRunner(make_app(loader, token), access_log=None)
    await runner.setup()
    try:
        await aioweb.TCPSite(runner, host, port).start()
    except OSError as e:
        await runner.cleanup()
        log.warning("Панель состояния не запущена на %s:%d: %s", host, port, e)
        return None
    shown_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    # The token goes to the console only: the log file can be sent to chats with .logs.
    lines = ["", "Панель состояния (только чтение):", f"  http://{shown_host}:{port}/?token={token}", ""]
    if host != DEFAULT_HOST:
        lines += ["Панель доступна не только с этого компьютера: не показывайте ссылку посторонним.", ""]
    print("\n".join(lines), flush=True)
    log.info("Панель состояния: http://%s:%d", host, port)
    return runner
