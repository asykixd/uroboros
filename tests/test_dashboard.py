import asyncio
import socket
from types import SimpleNamespace

from aiohttp.test_utils import TestClient, TestServer

from uroboros import dashboard

TOKEN = "t0ken"
EVIL = "<script>alert(1)</script>"


def fetch(loader, path):
    async def scenario():
        async with TestClient(TestServer(dashboard.make_app(loader, TOKEN))) as http:
            response = await http.get(path)
            return response.status, response.headers, await response.text()

    return asyncio.run(scenario())


def test_requires_token(builtin_loader):
    for path in ("/", "/?token=wrong", f"/?token={TOKEN}x"):
        status, _, body = fetch(builtin_loader, path)
        assert status == 403 and "Нет доступа" in body and "Модули" not in body
    status, headers, body = fetch(builtin_loader, f"/?token={TOKEN}")
    assert status == 200 and "📦 Модули" in body and "<b>Help</b>" in body
    assert (
        "script-src" not in headers["Content-Security-Policy"]
        and "default-src 'none'" in headers["Content-Security-Policy"]
    )
    assert headers["X-Frame-Options"] == "DENY" and headers["Cache-Control"] == "no-store"
    assert fetch(builtin_loader, f"/config.json?token={TOKEN}")[0] == 404  # nothing but the page itself


def test_everything_is_escaped(builtin_loader, monkeypatch):
    loader = builtin_loader
    asyncio.run(loader.install("from uroboros import Module\nclass Plain(Module):\n    pass\n", f"file:{EVIL}.py"))
    loader.failures["broken"] = EVIL
    loader.tampered.add(EVIL)
    loader.inline = SimpleNamespace(ready=False, error=EVIL, release=lambda stem: None)
    monkeypatch.setattr(dashboard.logs, "log_files", lambda: ["uroboros.log"])
    monkeypatch.setattr(dashboard.logs, "read", lambda level=0: ["first", f"2026-01-01 [ERROR] x: {EVIL}"])

    _, _, body = fetch(loader, f"/?token={TOKEN}")
    assert "<script>" not in body and body.count("&lt;script&gt;") == 5
    assert "<b>Plain</b>" in body and "⚠️ Проблемы" in body and "first" in body


def test_inline_states(builtin_loader):
    assert "Inline-бот не подключён" in fetch(builtin_loader, f"/?token={TOKEN}")[2]
    builtin_loader.inline = SimpleNamespace(ready=True, bot_username="my_bot", release=lambda stem: None)
    assert "Работает: @my_bot" in fetch(builtin_loader, f"/?token={TOKEN}")[2]


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_start_prints_link_and_survives_busy_port(builtin_loader, capsys, caplog):
    async def scenario():
        port = free_port()
        runner = await dashboard.start(builtin_loader, "127.0.0.1", port)
        try:
            assert runner is not None
            assert await dashboard.start(builtin_loader, "127.0.0.1", port) is None  # busy: bot keeps running
        finally:
            await runner.cleanup()
        return port

    port = asyncio.run(scenario())
    out = capsys.readouterr().out
    assert f"http://127.0.0.1:{port}/?token=" in out and "не показывайте" not in out
    assert "token=" not in caplog.text and "не запущена" in caplog.text
