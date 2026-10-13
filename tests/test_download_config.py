import asyncio
import io
import json
import os
import stat
import urllib.error

import pytest

from uroboros import config, download
from uroboros.errors import LoadError

API_HASH = "0123456789abcdef0123456789abcdef"


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def serve(monkeypatch, answer):
    def fake_open(request, timeout):
        assert request.get_header("User-agent") == "Uroboros" and timeout == 30
        if isinstance(answer, Exception):
            raise answer
        return Response(answer)

    monkeypatch.setattr(download._opener, "open", fake_open)


def test_download_source(monkeypatch):
    serve(monkeypatch, b"x = 1\n")
    assert asyncio.run(download.download_source("https://example.com/m.py")) == "x = 1\n"


@pytest.mark.parametrize(
    ("answer", "error"),
    [
        (b"x" * (download.MAX_SIZE + 1), "больше 2 МБ"),
        (urllib.error.HTTPError("u", 404, "nf", {}, None), "Не найдено"),
        (urllib.error.HTTPError("u", 500, "err", {}, None), "HTTP 500"),
        (OSError("сеть недоступна"), "сеть недоступна"),
    ],
)
def test_download_errors(monkeypatch, answer, error):
    serve(monkeypatch, answer)
    with pytest.raises(LoadError, match=error):
        asyncio.run(download.download("https://example.com/m.py"))


def test_download_rejects_non_utf8(monkeypatch):
    serve(monkeypatch, b"\xff\xfe")
    with pytest.raises(LoadError, match="UTF-8"):
        asyncio.run(download.download_source("https://example.com/m.py"))


def test_redirect_to_http_is_refused():
    handler = download._HttpsOnlyRedirect()
    with pytest.raises(LoadError, match="не на https"):
        handler.redirect_request(None, None, 302, "Found", {}, "http://evil.example/m.py")


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("UROBOROS_DATA", str(tmp_path / "data"))
    monkeypatch.delenv("UROBOROS_API_ID", raising=False)
    monkeypatch.delenv("UROBOROS_API_HASH", raising=False)
    return tmp_path / "data"


def test_config_from_file_and_env(data_dir, monkeypatch):
    assert config.load_config(prompt=False) is None
    config.save_credentials(data_dir, 1, API_HASH)
    cfg = config.load_config(prompt=False)
    assert (cfg.api_id, cfg.api_hash, cfg.data_dir) == (1, API_HASH, data_dir.resolve())
    assert cfg.db_path.name == "uroboros.db" and cfg.modules_dir.name == "modules"
    assert cfg.session_path.name == "uroboros" and cfg.lock_path.name == "uroboros.lock"
    assert cfg.log_path.name == "uroboros.log"

    monkeypatch.setenv("UROBOROS_API_ID", "2")
    assert config.load_config(prompt=False).api_id == 2


@pytest.mark.skipif(os.name != "posix", reason="права доступа POSIX")
def test_secrets_are_private(data_dir):
    config.save_credentials(config.get_data_dir(), 1, API_HASH)
    assert stat.S_IMODE(data_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE((data_dir / "config.json").stat().st_mode) == 0o600


def test_config_prompts_until_valid(data_dir, monkeypatch, capsys):
    answers = iter(["abc", "nothex", "123", API_HASH.upper()])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    cfg = config.load_config()
    assert (cfg.api_id, cfg.api_hash) == (123, API_HASH)
    assert "Попробуйте ещё раз" in capsys.readouterr().out
    assert json.loads((data_dir / "config.json").read_text("utf-8")) == {"api_id": 123, "api_hash": API_HASH}
