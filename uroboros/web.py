"""Веб-панель первого входа: api_id/api_hash → номер → код → пароль 2FA, или вход по QR-коду.

Поднимается, только если нет сессии, и выключается сразу после входа. По умолчанию слушает
``127.0.0.1``; каждый запрос должен нести одноразовый токен из ссылки, которую бот пишет в консоль.
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import html
import logging
import secrets
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiohttp import web

from .config import Config, save_credentials, valid_credentials

if TYPE_CHECKING:
    from telethon import TelegramClient

log = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080
QR_REFRESH = 3  # как часто страница с QR-кодом проверяет, отсканирован ли он
FINISH_DELAY = 1  # успеть отдать страницу «Готово» перед выключением


def _error_text(error: Exception) -> str:
    from telethon import errors

    known = {
        errors.ApiIdInvalidError: "Неверные api_id и api_hash: проверьте их на my.telegram.org",
        errors.PhoneNumberInvalidError: "Неверный номер телефона",
        errors.PhoneNumberBannedError: "Этот номер заблокирован в Telegram",
        errors.PhoneNumberUnoccupiedError: "На этот номер нет аккаунта Telegram",
        errors.PhoneCodeInvalidError: "Неверный код",
        errors.PhoneCodeExpiredError: "Код устарел, запросите новый",
        errors.PasswordHashInvalidError: "Неверный пароль",
    }
    for cls, text in known.items():
        if isinstance(error, cls):
            return text
    if isinstance(error, errors.FloodWaitError):
        return f"Telegram просит подождать {error.seconds} с перед следующей попыткой"
    return f"Ошибка Telegram: {error}"


class LoginFlow:
    """Шаги входа. Состояние: ``api``, ``phone``, ``code``, ``password``, ``qr``, ``done``."""

    def __init__(
        self,
        data_dir: Path,
        config: Config | None,
        client: TelegramClient | None = None,
        client_factory: Callable[[Config], Any] | None = None,
    ):
        self.data_dir = data_dir
        self.config = config
        self.client = client
        self.client_factory = client_factory
        self.state = "api" if config is None else "phone"
        self.error: str | None = None
        self.phone: str | None = None
        self.phone_code_hash: str | None = None
        self.qr: Any = None
        self.qr_task: asyncio.Task | None = None
        self.done = asyncio.Event()

    async def _get_client(self) -> TelegramClient:
        if self.client is None:
            if self.client_factory is None:
                from .client import make_client

                self.client_factory = make_client
            self.client = self.client_factory(self.config)
            await self.client.connect()
        return self.client

    async def _step(self, coro_func: Callable[[], Any]) -> None:
        self.error = None
        try:
            await coro_func()
        except Exception as e:
            from telethon.errors import ApiIdInvalidError, RPCError

            if not isinstance(e, RPCError):
                log.exception("Ошибка входа")
            self.error = _error_text(e)
            if isinstance(e, ApiIdInvalidError):
                await self._reset_client()
                self.config = None
                self.state = "api"

    async def _reset_client(self) -> None:
        if self.client is not None:
            with contextlib.suppress(Exception):
                await self.client.disconnect()
        self.client = None

    # --- шаги ---

    async def set_api(self, api_id: str, api_hash: str) -> None:
        api_id, api_hash = api_id.strip(), api_hash.strip().lower()
        if not valid_credentials(api_id, api_hash):
            self.error = "api_id — число, api_hash — 32 символа из 0-9 и a-f"
            return
        self.error = None
        save_credentials(self.data_dir, int(api_id), api_hash)
        await self._reset_client()
        self.config = Config(api_id=int(api_id), api_hash=api_hash, data_dir=self.data_dir)
        self.state = "phone"

    async def send_code(self, phone: str) -> None:
        phone = "".join(ch for ch in phone if ch.isdigit() or ch == "+")

        async def step() -> None:
            client = await self._get_client()
            sent = await client.send_code_request(phone)
            self.phone, self.phone_code_hash = phone, sent.phone_code_hash
            self.state = "code"

        await self._step(step)

    async def sign_in_code(self, code: str) -> None:
        from telethon.errors import SessionPasswordNeededError

        async def step() -> None:
            client = await self._get_client()
            try:
                await client.sign_in(phone=self.phone, code=code.strip(), phone_code_hash=self.phone_code_hash)
            except SessionPasswordNeededError:
                self.state = "password"
                return
            self._finish()

        await self._step(step)

    async def sign_in_password(self, password: str) -> None:
        async def step() -> None:
            client = await self._get_client()
            await client.sign_in(password=password)
            self._finish()

        await self._step(step)

    async def start_qr(self) -> None:
        async def step() -> None:
            client = await self._get_client()
            self.qr = await client.qr_login()
            self.state = "qr"
            if self.qr_task is None or self.qr_task.done():
                self.qr_task = asyncio.get_running_loop().create_task(self._wait_qr())

        await self._step(step)

    async def _wait_qr(self) -> None:
        from telethon.errors import SessionPasswordNeededError

        while self.state == "qr":
            try:
                await self.qr.wait()
            except asyncio.TimeoutError:
                await self._step(self.qr.recreate)  # код живёт ~30 с — показываем новый
                continue
            except SessionPasswordNeededError:
                self.state = "password"
                return
            except Exception as e:
                self.error = _error_text(e)
                self.state = "phone"
                return
            self._finish()
            return

    async def back(self) -> None:
        self.error = None
        if self.qr_task is not None:
            self.qr_task.cancel()
        self.state = "api" if self.config is None else "phone"

    def _finish(self) -> None:
        self.state = "done"
        self.error = None
        self.done.set()


# --- страницы ---

STYLE = """
:root { --bg: #f4f5f7; --card: #fff; --text: #1d1f23; --muted: #6b7079; --accent: #2b7de9; --error: #c93c3c;
        --border: #dfe2e6; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #15171a; --card: #1f2226; --text: #e8eaed; --muted: #9aa0a8; --accent: #5aa0ff; --error: #ff7b7b;
          --border: #33373d; }
}
* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 16px;
       background: var(--bg); color: var(--text); font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { width: 100%; max-width: 380px; background: var(--card); border: 1px solid var(--border); border-radius: 14px;
       padding: 28px 24px; }
h1 { font-size: 20px; margin: 0 0 4px; }
p { margin: 0 0 16px; color: var(--muted); font-size: 14px; }
label { display: block; font-size: 13px; color: var(--muted); margin: 12px 0 4px; }
input { width: 100%; padding: 10px 12px; border: 1px solid var(--border); border-radius: 8px; font: inherit;
        background: var(--bg); color: var(--text); }
button { width: 100%; margin-top: 16px; padding: 11px; border: 0; border-radius: 8px; font: inherit; font-weight: 600;
         background: var(--accent); color: #fff; cursor: pointer; }
button.link { background: none; color: var(--accent); font-weight: 400; margin-top: 8px; padding: 6px; }
.error { color: var(--error); font-size: 14px; margin: 0 0 12px; }
.qr { background: #fff; padding: 12px; border-radius: 10px; margin: 0 auto 16px; width: 232px; }
.qr svg { display: block; width: 208px; height: 208px; }
a { color: var(--accent); }
"""


def _form(token: str, action: str, body: str, submit: str) -> str:
    return (
        f'<form method="post" action="/"><input type="hidden" name="token" value="{token}">'
        f'<input type="hidden" name="action" value="{action}">{body}<button type="submit">{submit}</button></form>'
    )


def _link_button(token: str, action: str, text: str) -> str:
    return (
        f'<form method="post" action="/"><input type="hidden" name="token" value="{token}">'
        f'<input type="hidden" name="action" value="{action}"><button class="link" type="submit">{text}</button></form>'
    )


def _qr_svg(url: str) -> str:
    import qrcode
    import qrcode.image.svg

    image = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, border=1)
    return image.to_string(encoding="unicode")


def render(flow: LoginFlow, token: str) -> str:
    error = f'<p class="error">{html.escape(flow.error)}</p>' if flow.error else ""
    refresh = ""
    if flow.state == "api":
        body = (
            "<h1>Uroboros</h1><p>Получите api_id и api_hash на "
            '<a href="https://my.telegram.org/apps" target="_blank" rel="noreferrer">my.telegram.org/apps</a></p>'
            + error
            + _form(
                token,
                "api",
                '<label for="api_id">api_id</label><input id="api_id" name="api_id" inputmode="numeric" required>'
                '<label for="api_hash">api_hash</label><input id="api_hash" name="api_hash" required>',
                "Дальше",
            )
        )
    elif flow.state == "phone":
        body = (
            "<h1>Вход в Telegram</h1><p>Номер телефона аккаунта, на котором будет работать юзербот</p>"
            + error
            + _form(
                token,
                "phone",
                '<label for="phone">Номер</label>'
                '<input id="phone" name="phone" type="tel" placeholder="+7 900 000-00-00" autocomplete="tel" required>',
                "Получить код",
            )
            + _link_button(token, "qr", "Войти по QR-коду")
        )
    elif flow.state == "code":
        body = (
            f"<h1>Код</h1><p>Telegram прислал код на {html.escape(flow.phone or '')}: в приложение или по SMS</p>"
            + error
            + _form(
                token,
                "code",
                '<label for="code">Код</label>'
                '<input id="code" name="code" inputmode="numeric" autocomplete="one-time-code" required>',
                "Войти",
            )
            + _link_button(token, "back", "Другой номер")
        )
    elif flow.state == "password":
        body = (
            "<h1>Пароль</h1><p>На аккаунте включена двухэтапная проверка</p>"
            + error
            + _form(
                token,
                "password",
                '<label for="password">Облачный пароль</label>'
                '<input id="password" name="password" type="password" autocomplete="current-password" required>',
                "Войти",
            )
        )
    elif flow.state == "qr":
        refresh = f'<meta http-equiv="refresh" content="{QR_REFRESH}; url=/?token={token}">'
        body = (
            "<h1>Вход по QR-коду</h1><p>Telegram на телефоне → Настройки → Устройства → Подключить устройство</p>"
            + error
            + f'<div class="qr">{_qr_svg(flow.qr.url)}</div>'
            + _link_button(token, "back", "Войти по номеру")
        )
    else:
        body = "<h1>Готово</h1><p>Вход выполнен, юзербот запускается. Это окно можно закрыть.</p>"
    return (
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<meta name="referrer" content="no-referrer">{refresh}<title>Uroboros — вход</title>'
        f"<style>{STYLE}</style></head><body><main>{body}</main></body></html>"
    )


DENIED = (
    '<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Uroboros</title></head>'
    "<body><p>Нет доступа: откройте ссылку из консоли Uroboros целиком.</p></body></html>"
)


def make_app(flow: LoginFlow, token: str) -> web.Application:
    def allowed(given: str | None) -> bool:
        return given is not None and hmac.compare_digest(given, token)

    def page(text: str, status: int = 200) -> web.Response:
        return web.Response(
            text=text,
            status=status,
            content_type="text/html",
            headers={"Cache-Control": "no-store", "X-Frame-Options": "DENY"},
        )

    async def show(request: web.Request) -> web.Response:
        if not allowed(request.query.get("token")):
            return page(DENIED, 403)
        return page(render(flow, token))

    async def act(request: web.Request) -> web.Response:
        form = await request.post()
        if not allowed(form.get("token")):
            return page(DENIED, 403)
        action = form.get("action")
        if flow.state != "done":
            if action == "api":
                await flow.set_api(str(form.get("api_id", "")), str(form.get("api_hash", "")))
            elif action == "phone" and flow.state in ("phone", "code"):
                await flow.send_code(str(form.get("phone", "")))
            elif action == "code" and flow.state == "code":
                await flow.sign_in_code(str(form.get("code", "")))
            elif action == "password" and flow.state == "password":
                await flow.sign_in_password(str(form.get("password", "")))
            elif action == "qr":
                await flow.start_qr()
            elif action == "back":
                await flow.back()
        # После POST — на GET, чтобы обновление страницы не отправляло форму ещё раз.
        raise web.HTTPSeeOther(f"/?token={token}")

    app = web.Application()
    app.router.add_get("/", show)
    app.router.add_post("/", act)
    return app


async def first_login(
    config: Config | None,
    data_dir: Path,
    client: TelegramClient | None = None,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> tuple[Config, TelegramClient]:
    """Поднимает панель, ждёт входа и выключает её. Возвращает конфиг и подключённый клиент."""
    flow = LoginFlow(data_dir, config, client)
    token = secrets.token_urlsafe(24)
    runner = web.AppRunner(make_app(flow, token), access_log=None)
    await runner.setup()
    try:
        await web.TCPSite(runner, host, port).start()
    except OSError as e:
        await runner.cleanup()
        raise SystemExit(f"Не удалось открыть веб-панель на {host}:{port}: {e}. Другой порт: --port 8081") from e

    shown_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    url = f"http://{shown_host}:{port}/?token={token}"
    lines = ["", "Откройте в браузере, чтобы войти в Telegram:", f"  {url}", ""]
    if host == DEFAULT_HOST:
        lines += [
            "На сервере без браузера пробросьте порт со своего компьютера:",
            f"  ssh -L {port}:127.0.0.1:{port} пользователь@сервер",
            "и откройте ссылку у себя. Вход в консоли: --cli",
            "",
        ]
    else:
        lines += ["Панель доступна не только с этого компьютера: не показывайте ссылку посторонним.", ""]
    print("\n".join(lines), flush=True)
    log.info("Веб-панель входа: http://%s:%d", host, port)

    try:
        await flow.done.wait()
        await asyncio.sleep(FINISH_DELAY)
    finally:
        if flow.qr_task is not None:
            flow.qr_task.cancel()
        await runner.cleanup()
    log.info("Вход выполнен, веб-панель выключена")
    return flow.config, flow.client
