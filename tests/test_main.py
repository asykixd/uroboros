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
