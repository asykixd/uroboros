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


def test_cli_without_terminal_or_credentials_fails_fast(monkeypatch):
    monkeypatch.setattr(main.sys, "stdin", None)
    with pytest.raises(SystemExit, match="Войдите один раз вручную"):
        connect(monkeypatch, ["--cli"], None, authorized=False)


class RunClient:
    """Enough of UroborosClient for ``main.run``: records the startup sequence."""

    def __init__(self, events, fail_on=None):
        self.events = events
        self.fail_on = fail_on
        self.handlers = []
        self.limiter = self.guard = None

    async def get_me(self):
        self.events.append("get_me")
        return SimpleNamespace(id=42, first_name="Owner")

    def add_event_handler(self, callback, event=None):
        self.handlers.append((callback, event))

    def remove_event_handler(self, callback, event=None):
        self.handlers = [h for h in self.handlers if h[0] is not callback]

    def list_event_handlers(self):
        return list(self.handlers)

    async def run_until_disconnected(self):
        self.events.append("run")
        if self.fail_on == "run":
            raise ConnectionError("lost")

    async def disconnect(self):
        self.events.append("disconnect")


class FakeInline:
    def __init__(self, client, db):
        self.events = client.events
        self.loader = None
        self.error = None

    async def start(self):
        self.events.append("inline.start")

    async def stop(self):
        self.events.append("inline.stop")

    def release(self, stem):
        pass


def run_main(monkeypatch, tmp_path, seen, fail_on=None):
    events = seen.setdefault("events", [])
    client = seen["client"] = RunClient(events, fail_on)
    config = main.Config(api_id=1, api_hash="0" * 32, data_dir=tmp_path)
    activated = seen["activated"] = []

    async def fake_connect(args):
        events.append("connect")
        return config, client

    async def fake_login(c):
        events.append("login")

    async def fake_shutdown(loader):
        events.append("shutdown")
        await loader.unload_all()

    monkeypatch.setattr(main, "connect", fake_connect)
    monkeypatch.setattr(main, "login", fake_login)
    monkeypatch.setattr(main, "InlineManager", FakeInline)
    monkeypatch.setattr(main, "shutdown", fake_shutdown)
    # The real audit hook can't be removed once installed: it would outlive the test.
    monkeypatch.setattr(main.guard, "activate", activated.append)
    monkeypatch.setattr(main, "handle_sigterm", lambda c: events.append("sigterm"))
    real_load_all = main.Loader.load_all

    async def load_all(self):
        events.append("load_all")
        seen["loader"] = self
        await real_load_all(self)
        seen["commands"] = set(self.commands)

    monkeypatch.setattr(main.Loader, "load_all", load_all)
    asyncio.run(main.run(main.parse_args([])))


def test_run_wires_components_in_order(monkeypatch, tmp_path):
    seen = {}
    run_main(monkeypatch, tmp_path, seen)
    loader, client = seen["loader"], seen["client"]
    assert seen["events"] == [
        "connect",
        "login",
        "get_me",
        "inline.start",
        "load_all",
        "sigterm",
        "run",
        "shutdown",
        "inline.stop",
        "disconnect",
    ]
    assert seen["activated"] == [loader.guard]
    assert client.limiter is loader.ratelimit and client.guard is loader.guard
    assert loader.security.me_id == 42 and loader.inline.loader is loader
    assert "help" in seen["commands"] and not loader.modules  # loaded, then unloaded on shutdown
    assert any(event is not None for _, event in client.handlers)  # dispatcher installed
    assert (tmp_path / "uroboros.db").exists()


def test_run_cleans_up_when_connection_drops(monkeypatch, tmp_path):
    seen = {}
    with pytest.raises(ConnectionError):
        run_main(monkeypatch, tmp_path, seen, fail_on="run")
    assert seen["events"][-4:] == ["run", "shutdown", "inline.stop", "disconnect"]


def prepare_main(monkeypatch, tmp_path, run):
    monkeypatch.setattr(main.utils, "IS_WINDOWS", False)
    monkeypatch.setattr(main.sys, "argv", ["uroboros"])
    monkeypatch.setattr(main, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main.logs, "setup", lambda path: None)
    monkeypatch.setattr(main, "run", run)


def test_main_refuses_second_instance(monkeypatch, tmp_path):
    async def run(args):
        raise AssertionError("must not start")

    prepare_main(monkeypatch, tmp_path, run)
    held = main.InstanceLock(tmp_path / "uroboros.lock")
    assert held.acquire()
    try:
        with pytest.raises(SystemExit, match="уже запущен"):
            main.main()
    finally:
        held.release()


def test_main_releases_lock_and_restarts(monkeypatch, tmp_path):
    restarted = []

    async def run(args):
        pass

    prepare_main(monkeypatch, tmp_path, run)
    monkeypatch.setattr(main.utils, "restart_requested", lambda: True)
    monkeypatch.setattr(main.utils, "exec_restart", lambda: restarted.append(True))
    main.main()
    assert restarted == [True]
    lock = main.InstanceLock(tmp_path / "uroboros.lock")
    assert lock.acquire()  # released before the restart
    lock.release()
