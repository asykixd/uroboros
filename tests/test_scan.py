import asyncio

import pytest
from conftest import FakeMessage

from uroboros import backup, download, scan

SAFE = """
from uroboros import Module, command

class Demo(Module):
    \"\"\"Не трогает файл .session — это просто докстринг\"\"\"

    @command("one")
    async def one(self, m):
        pass
"""
STEALER = SAFE.replace(
    "        pass\n",
    "        await self.client.send_message('me', self.client.session.save())\n",
)


def texts(source, level):
    return {f.text for f in scan.scan(source).findings if f.level == level}


def test_safe_module_has_no_findings():
    assert scan.scan(SAFE).findings == []


@pytest.mark.parametrize(
    ("code", "text"),
    [
        ("from telethon.tl.functions.auth import ResetAuthorizationsRequest as R", "завершает все другие сеансы"),
        ("getattr(functions.account, 'DeleteAccountRequest')", "удаляет аккаунт"),
        ("client.session.save()", "выгружает сессию в строку"),
        ("StringSession.save(client.session)", "выгружает сессию в строку"),
        ("x[0].auth_key", "ключ авторизации"),
        ("open('data/uroboros.session', 'rb')", "файлу сессии"),
        ("import base64 as b\nexec(b.b64decode(blob))", "закодированный код"),
        ("import marshal\nmarshal.loads(data)", "marshal"),
        ("self.loader.security.owner = 1", "права доступа"),
        ("db.get('uroboros.inline', 'token')", "токен бота"),
        ("await client.log_out()", "выходит из аккаунта"),
    ],
)
def test_dangerous(code, text):
    assert any(text in found for found in texts(code, scan.DANGER)), texts(code, scan.DANGER)


@pytest.mark.parametrize(
    ("code", "text"),
    [
        ("import os\nos.environ['X']", "переменные окружения"),
        ("from os import getenv\ngetenv('X')", "переменные окружения"),
        ("import subprocess\nsubprocess.run(['ls'])", "команды в системе"),
        ("open('config.json')", "config.json"),
        ("eval(expr)", "код из строки"),
        ("await self.client(JoinChannelRequest(ch))", "подписывает аккаунт"),
    ],
)
def test_warnings(code, text):
    assert any(text in found for found in texts(code, scan.WARNING)), texts(code, scan.WARNING)
    assert not texts(code, scan.DANGER)


def test_lines_are_merged_and_described():
    report = scan.scan("import os\nos.environ\nos.environ\n")
    assert scan.describe(report.warnings) == "строки 2, 3: читает переменные окружения"


def test_syntax_error_is_left_to_compile():
    assert scan.scan("def (").findings == []


def test_install_blocks_dangerous_without_force(builtin_loader):
    loader = builtin_loader
    with pytest.raises(scan.UnsafeModuleError, match="выгружает сессию"):
        asyncio.run(loader.install(STEALER, "https://example.com/demo.py"))
    assert loader.get_module("demo") is None
    asyncio.run(loader.install(STEALER, "https://example.com/demo.py", force=True))
    assert loader.get_module("demo") is not None


def run_command(loader, text, reply=None):
    message = FakeMessage(text)
    if reply is not None:

        async def get_reply_message():
            return reply

        message.get_reply_message = get_reply_message
    asyncio.run(loader.get_command(text.split()[0][1:]).func(message))
    return message.edits[-1]


def test_dlm_from_trusted_repo_still_asks_for_dangerous(builtin_loader, monkeypatch):
    loader = builtin_loader

    async def fake_download(url):
        return STEALER.encode()

    monkeypatch.setattr(download, "download", fake_download)
    loader.get_module("loader").db.set("repos", ["someone/mods"])
    text = run_command(loader, ".dlm someone/mods/demo")
    assert text.startswith("❌ <b>Модуль может навредить аккаунту") and "выгружает сессию" in text
    assert "dlm -f someone/mods/demo" in text and loader.get_module("demo") is None

    text = run_command(loader, ".dlm -f someone/mods/demo")
    assert text.startswith("✅") and "<b>Опасное:</b>" in text


def test_uplm_skips_dangerous_update(builtin_loader, monkeypatch):
    loader = builtin_loader
    asyncio.run(loader.install(SAFE, "https://example.com/demo.py"))

    async def fake_download(url):
        return STEALER.encode()

    monkeypatch.setattr(download, "download", fake_download)
    text = run_command(loader, ".uplm demo")
    assert text.startswith("❌ <b>В обновлениях модулей опасный код") and "выгружает сессию" in text
    assert "uplm -f demo" in text and "save" not in (loader.modules_dir / "demo.py").read_text()

    assert "обновлён" in run_command(loader, ".uplm -f demo")
    assert "save" in (loader.modules_dir / "demo.py").read_text()


def test_restore_refuses_dangerous_modules(builtin_loader):
    loader = builtin_loader
    asyncio.run(loader.install(STEALER, "https://example.com/demo.py", force=True))
    data = backup.create(loader.db, loader.modules_dir)

    class Reply:
        class file:
            size = len(data)

        async def download_media(self, _):
            return data

    restarted = []

    async def fake_restart(msg):
        restarted.append(msg)

    loader.get_module("System").restart = fake_restart
    text = run_command(loader, ".restore", Reply())
    assert text.startswith("❌") and "<b>demo</b>: выгружает сессию" in text and "restore -f" in text
    assert restarted == []

    assert run_command(loader, ".restore -f", Reply()).startswith("✅")
    assert len(restarted) == 1


def test_tampered_module_file(builtin_loader, caplog):
    loader = builtin_loader
    asyncio.run(loader.install(SAFE, "https://example.com/demo.py"))
    path = loader.modules_dir / "demo.py"

    path.write_text(SAFE.replace("pass", "return 1"))
    asyncio.run(loader.reload_all())
    assert loader.get_module("demo") is not None and "изменён не через Uroboros" in caplog.text

    path.write_text(STEALER)
    asyncio.run(loader.reload_all())
    assert loader.get_module("demo") is None and "опасный код" in caplog.text

    # Переустановка через Uroboros — новый хеш, модуль снова грузится.
    asyncio.run(loader.install(STEALER, "https://example.com/demo.py", force=True))
    asyncio.run(loader.reload_all())
    assert loader.get_module("demo") is not None
