import asyncio
from types import SimpleNamespace

import pytest

from uroboros import main
from uroboros.config import Config

CONFIG = Config(api_id=1, api_hash="0" * 32, data_dir=None)


class Client:
    def __init__(self, authorized):
        self.authorized = authorized

    async def connect(self):
        pass

    async def is_user_authorized(self):
        return self.authorized

    async def disconnect(self):
        pass


def connect(monkeypatch, argv, config, authorized):
    calls = []

    async def fake_first_login(cfg, data_dir, client, *, host, port):
        calls.append((cfg, client, host, port))
        return CONFIG, client or "new client"

    monkeypatch.setattr(main, "load_config", lambda prompt: config)
    monkeypatch.setattr(main, "make_client", lambda cfg: Client(authorized))
    monkeypatch.setattr(main, "get_data_dir", lambda: "data")
    monkeypatch.setattr(main.web, "first_login", fake_first_login)
    result = asyncio.run(main.connect(main.parse_args(argv)))
    return result, calls


def test_authorized_session_skips_panel(monkeypatch):
    (_, client), calls = connect(monkeypatch, [], CONFIG, authorized=True)
    assert calls == [] and client.authorized


def test_no_session_opens_panel(monkeypatch):
    (_, client), calls = connect(monkeypatch, ["--port", "9000"], CONFIG, authorized=False)
    assert calls[0][2:] == ("127.0.0.1", 9000) and calls[0][1] is client


def test_no_credentials_opens_panel(monkeypatch):
    (_, client), calls = connect(monkeypatch, [], None, authorized=False)
    assert calls[0][0] is None and client == "new client"


def test_cli_never_opens_panel(monkeypatch):
    monkeypatch.setattr(main.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    (_, client), calls = connect(monkeypatch, ["--cli"], CONFIG, authorized=False)
    assert calls == [] and not client.authorized


def test_cli_without_terminal_explains_how_to_log_in(monkeypatch):
    monkeypatch.setattr(main.sys, "stdin", SimpleNamespace(isatty=lambda: False))
    with pytest.raises(SystemExit, match="Войдите один раз вручную"):
        connect(monkeypatch, ["--cli"], CONFIG, authorized=False)


class Saved:
    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    async def send_message(self, chat, text, **kwargs):
        if self.fail:
            raise ConnectionError("offline")
        self.sent.append((chat, text))


def test_notifications_go_to_saved_messages(caplog):
    async def scenario(client):
        main.notify_frozen(client, "Spam<b>", {"limit": 60, "window": 30, "freeze": 300})
        main.notify_blocked(client, "Evil", "удалить аккаунт")
        await asyncio.sleep(0)

    client = Saved()
    asyncio.run(scenario(client))
    (frozen, blocked) = client.sent
    assert frozen[0] == "me" and "Spam&lt;b&gt;" in frozen[1] and "60" in frozen[1]
    assert "удалить аккаунт" in blocked[1] and "security trust Evil" in blocked[1]

    asyncio.run(scenario(Saved(fail=True)))
    assert "Не удалось сообщить" in caplog.text
    main.notify_blocked(Saved(), "Evil", "x")  # вне цикла событий — только лог


def test_shutdown_does_not_hang_on_stuck_module(monkeypatch, caplog):
    monkeypatch.setattr(main, "UNLOAD_TIMEOUT", 0.01)

    class Stuck:
        async def unload_all(self):
            await asyncio.sleep(10)

    class Broken:
        async def unload_all(self):
            raise RuntimeError("boom")

    asyncio.run(main.shutdown(Stuck()))
    asyncio.run(main.shutdown(Broken()))
    assert "не выгрузились" in caplog.text and "Ошибка при выгрузке" in caplog.text
