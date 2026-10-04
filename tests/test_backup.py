import asyncio
import io
import json
import zipfile

import pytest
from conftest import FakeMessage

from uroboros import backup
from uroboros.database import LOADER_OWNER, MAIN_OWNER, Database
from uroboros.loader import Loader
from uroboros.validators import ValidationError

MODULE = "from uroboros import Module\nclass Demo(Module):\n    pass\n"


@pytest.fixture
def db():
    database = Database(":memory:")
    yield database
    database.close()


def make_zip(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def test_roundtrip(db, tmp_path):
    src_dir, dst_dir = tmp_path / "src", tmp_path / "dst"
    asyncio.run(Loader(None, db, src_dir).install(MODULE, "https://example.com/demo.py"))
    db.set(MAIN_OWNER, "prefix", "!")
    data = backup.create(db, src_dir)

    (dst_dir).mkdir()
    (dst_dir / "stale.py").write_text("x = 1", encoding="utf-8")
    target = Database(":memory:")
    target.set("Old", "key", 1)
    restored = backup.restore(data, target, dst_dir)

    assert restored.modules == ["demo"]
    assert target.get(MAIN_OWNER, "prefix") == "!"
    assert target.get(LOADER_OWNER, "installed") == {"demo": "https://example.com/demo.py"}
    assert target.get("Old", "key") is None
    assert (dst_dir / "demo.py").read_text(encoding="utf-8") == MODULE
    assert not (dst_dir / "stale.py").exists()
    target.close()


def test_archive_never_contains_session(db, tmp_path):
    (tmp_path / "uroboros.session").write_text("secret", encoding="utf-8")
    names = zipfile.ZipFile(io.BytesIO(backup.create(db, tmp_path / "modules"))).namelist()
    assert names == [backup.MANIFEST, backup.DB_FILE]


@pytest.mark.parametrize(
    ("files", "error"),
    [
        ({"x": "1"}, "не бэкап"),
        ({"manifest.json": "{}", "db.json": "{}", "../../evil.py": "x"}, "Лишний файл"),
        ({"manifest.json": "{}", "db.json": "{}", "modules/A.py": "x"}, "Лишний файл"),
        ({"manifest.json": "{}", "db.json": "[1]"}, "структура"),
        ({"manifest.json": "{}", "db.json": "{bad"}, "Повреждён"),
        (
            {"manifest.json": "{}", "db.json": json.dumps({LOADER_OWNER: {"installed": {"gone": "x"}}})},
            "нет файлов модулей",
        ),
    ],
)
def test_bad_archives_are_rejected(db, tmp_path, files, error):
    with pytest.raises(backup.BackupError, match=error):
        backup.restore(make_zip(files), db, tmp_path)
    assert not tmp_path.joinpath("modules").exists()


def test_not_a_zip(db, tmp_path):
    with pytest.raises(backup.BackupError, match="не zip"):
        backup.restore(b"hello", db, tmp_path)


def test_restore_command_writes_db_in_main_thread(builtin_loader):
    loader = builtin_loader
    asyncio.run(loader.install(MODULE, "https://example.com/demo.py"))
    data = backup.create(loader.db, loader.modules_dir)

    class Reply:
        class file:
            size = len(data)

        async def download_media(self, _):
            return data

    message = FakeMessage(".restore")

    async def get_reply_message():
        return Reply()

    message.get_reply_message = get_reply_message
    restarted = []

    async def fake_restart(msg):
        restarted.append(msg)

    loader.get_module("System").restart = fake_restart
    asyncio.run(loader.get_command("restore").func(message))
    assert message.edits[-1].startswith("✅")
    assert restarted == [message]


def test_autobackup_schedule(builtin_loader):
    import time

    module = builtin_loader.get_module("backup")
    sent = []

    class Client:
        async def send_file(self, chat, file, **kwargs):
            sent.append((chat, file.name))

    module.client = Client()
    asyncio.run(module.autobackup())
    assert sent == []  # по умолчанию выключен

    module.config["interval"] = "6"
    module.config["chat"] = "-1001234"
    asyncio.run(module.autobackup())
    asyncio.run(module.autobackup())  # следующий — только через 6 часов
    assert len(sent) == 1 and sent[0][0] == -1001234 and sent[0][1].endswith(".zip")

    module.db.set("last_auto", time.time() - 6 * 3600 - 1)
    asyncio.run(module.autobackup())
    assert len(sent) == 2

    with pytest.raises(ValidationError):
        module.config["chat"] = "куда-то"
