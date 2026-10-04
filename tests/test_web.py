import asyncio
import json
import re
from types import SimpleNamespace

import pytest
from aiohttp.test_utils import TestClient, TestServer
from telethon import errors

from uroboros import web
from uroboros.config import Config

API_HASH = "0123456789abcdef0123456789abcdef"


class FakeQR:
    url = "tg://login?token=abc"

    def __init__(self):
        self.result = asyncio.get_running_loop().create_future()

    async def wait(self, timeout=None):
        return await self.result

    async def recreate(self):
        pass


class FakeTelegram:
    """Клиент Telethon для входа: код 12345, пароль secret у номера с 2FA."""

    def __init__(self, two_factor=False):
        self.two_factor = two_factor
        self.connected = False
        self.signed_in = False
        self.qr = None

    async def connect(self):
        self.connected = True

    async def disconnect(self):
        self.connected = False

    async def send_code_request(self, phone):
        if phone != "+79000000000":
            raise errors.PhoneNumberInvalidError(request=None)
        return SimpleNamespace(phone_code_hash="hash")

    async def sign_in(self, phone=None, code=None, *, password=None, phone_code_hash=None):
        if password is not None:
            if password != "secret":
                raise errors.PasswordHashInvalidError(request=None)
        else:
            assert phone_code_hash == "hash"
            if code != "12345":
                raise errors.PhoneCodeInvalidError(request=None)
            if self.two_factor:
                raise errors.SessionPasswordNeededError(request=None)
        self.signed_in = True

    async def qr_login(self):
        self.qr = FakeQR()
        return self.qr


def make_flow(tmp_path, config=None, telegram=None):
    telegram = telegram or FakeTelegram()
    flow = web.LoginFlow(tmp_path, config, client_factory=lambda cfg: telegram)
    return flow, telegram


def config(tmp_path):
    return Config(api_id=1, api_hash=API_HASH, data_dir=tmp_path)


def test_api_step_saves_credentials(tmp_path):
    async def scenario():
        flow, _ = make_flow(tmp_path)
        assert flow.state == "api"
        await flow.set_api("abc", "nothex")
        assert flow.state == "api" and "api_id" in flow.error
        await flow.set_api(" 123 ", API_HASH.upper())
        assert flow.state == "phone" and flow.config.api_id == 123

    asyncio.run(scenario())
    assert json.loads((tmp_path / "config.json").read_text(encoding="utf-8")) == {"api_id": 123, "api_hash": API_HASH}


def test_phone_code_password(tmp_path):
    async def scenario():
        flow, telegram = make_flow(tmp_path, config(tmp_path), FakeTelegram(two_factor=True))
        await flow.send_code("+7 900 000-00-01")
        assert flow.state == "phone" and flow.error == "Неверный номер телефона"
        await flow.send_code("+7 (900) 000-00-00")
        assert flow.state == "code" and telegram.connected
        await flow.sign_in_code("11111")
        assert flow.state == "code" and flow.error == "Неверный код"
        await flow.sign_in_code("12345")
        assert flow.state == "password"
        await flow.sign_in_password("wrong")
        assert flow.error == "Неверный пароль" and not flow.done.is_set()
        await flow.sign_in_password("secret")
        assert flow.state == "done" and flow.done.is_set() and telegram.signed_in

    asyncio.run(scenario())


def test_qr_login(tmp_path):
    async def scenario():
        flow, telegram = make_flow(tmp_path, config(tmp_path))
        await flow.start_qr()
        assert flow.state == "qr" and "<svg" in web.render(flow, "t")
        telegram.qr.result.set_exception(errors.SessionPasswordNeededError(request=None))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert flow.state == "password"

        await flow.back()
        await flow.start_qr()
        telegram.qr.result.set_result(True)
        await asyncio.wait_for(flow.done.wait(), 1)

    asyncio.run(scenario())


def test_http_requires_token(tmp_path):
    async def scenario():
        flow, _ = make_flow(tmp_path, config(tmp_path))
        token = "tok"
        async with TestClient(TestServer(web.make_app(flow, token))) as http:
            assert (await http.get("/")).status == 403
            assert (await http.get("/?token=bad")).status == 403
            denied = await http.post("/", data={"token": "bad", "action": "phone", "phone": "+79000000000"})
            assert denied.status == 403 and flow.state == "phone"

            page = await (await http.get(f"/?token={token}")).text()
            assert 'name="phone"' in page and f'value="{token}"' in page

            response = await http.post("/", data={"token": token, "action": "phone", "phone": "+79000000000"})
            assert response.status == 200 and str(response.url).endswith(f"/?token={token}")
            assert 'name="code"' in await response.text()

            response = await http.post("/", data={"token": token, "action": "code", "code": "12345"})
            assert "Готово" in await response.text() and flow.done.is_set()

    asyncio.run(scenario())


def test_render_escapes_errors(tmp_path):
    flow, _ = make_flow(tmp_path, config(tmp_path))
    flow.error = "<script>"
    page = web.render(flow, "t")
    assert "<script>" not in page and "&lt;script&gt;" in page


def test_first_login_returns_after_sign_in(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "FINISH_DELAY", 0)
    monkeypatch.setattr("builtins.print", lambda *a, **k: None)
    flows = []

    class Flow(web.LoginFlow):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            flows.append(self)

    monkeypatch.setattr(web, "LoginFlow", Flow)
    telegram = FakeTelegram()

    async def scenario():
        task = asyncio.create_task(web.first_login(config(tmp_path), tmp_path, telegram, port=0))
        while not flows:
            await asyncio.sleep(0.01)
        await flows[0].send_code("+79000000000")
        await flows[0].sign_in_code("12345")
        return await asyncio.wait_for(task, 2)

    cfg, client = asyncio.run(scenario())
    assert cfg.api_id == 1 and client is telegram and telegram.signed_in


def test_link_format(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "FINISH_DELAY", 0)
    printed = []
    monkeypatch.setattr("builtins.print", lambda *a, **k: printed.append(" ".join(map(str, a))))

    async def scenario():
        telegram = FakeTelegram()
        task = asyncio.create_task(web.first_login(config(tmp_path), tmp_path, telegram, port=0))
        while not printed:
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    text = printed[0]
    assert re.search(r"http://127\.0\.0\.1:0/\?token=[\w-]{20,}", text) and "ssh -L" in text
