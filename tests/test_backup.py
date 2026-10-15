import asyncio
import io
import json
import zipfile

import pytest
from conftest import FakeMessage

from uroboros import backup
from uroboros.database import LOADER_OWNER, MAIN_OWNER, Database
from uroboros.loader import Loader
from uroboros.security import SECURITY_OWNER
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


def run_restore(loader, data, text=".restore"):
    class Reply:
        class file:
            size = len(data)

        async def download_media(self, _):
            return data

    message = FakeMessage(text)

    async def get_reply_message():
        return Reply()

    message.get_reply_message = get_reply_message
    restarted = []

    async def fake_restart(msg):
        restarted.append(msg)

    loader.get_module("System").restart = fake_restart
    asyncio.run(loader.get_command("restore").func(message))
    return message, restarted


def test_restore_command_writes_db_in_main_thread(builtin_loader):
    loader = builtin_loader
    loader.security.me_id = 1
    asyncio.run(loader.install(MODULE, "https://example.com/demo.py"))
    data = backup.create(loader.db, loader.modules_dir, owner=1)
    message, restarted = run_restore(loader, data)
    assert message.edits[-1].startswith("✅")
    assert restarted == [message]


def test_foreign_backup_needs_confirmation_and_keeps_account_settings(builtin_loader, tmp_path):
    loader = builtin_loader
    loader.security.me_id = 1
    loader.db.set(SECURITY_OWNER, "sudo", [5])
    loader.db.set("uroboros.inline", "token", "1:mine")

    other = Database(":memory:")
    other.set(SECURITY_OWNER, "owner", [666])
    other.set("uroboros.inline", "token", "2:theirs")
    other.set(LOADER_OWNER, "trusted", ["evil"])
    other.set(MAIN_OWNER, "prefix", "!")
    data = backup.create(other, tmp_path / "none", owner=2)
    other.close()

    message, restarted = run_restore(loader, data)
    assert "чужой бэкап" in message.edits[-1] and "<code>2</code>" in message.edits[-1] and not restarted
    assert loader.db.get(MAIN_OWNER, "prefix") is None

    message, restarted = run_restore(loader, data, ".restore -f")
    assert message.edits[-1].startswith("✅") and restarted
    assert loader.db.get(MAIN_OWNER, "prefix") == "!"
    assert loader.db.get(SECURITY_OWNER, "owner") is None and loader.db.get(SECURITY_OWNER, "sudo") == [5]
    assert loader.db.get("uroboros.inline", "token") == "1:mine"
    assert "evil" not in loader.db.get(LOADER_OWNER, "trusted", [])


def test_backup_without_owner_is_foreign():
    assert backup.Archive({}, {}, None).is_foreign(1)
    assert not backup.Archive({}, {}, 1).is_foreign(1)


def test_restored_db_ignores_writes_until_restart(db, tmp_path):
    data = backup.create(db, tmp_path / "modules")
    target = Database(":memory:")
    backup.restore(data, target, tmp_path / "dst")
    target.set("Backup", "last_auto", 1)
    target.delete(MAIN_OWNER, "prefix")
    assert target.get("Backup", "last_auto") is None
    target.close()


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


class SentFile:
    def __init__(self, message_id):
        self.id = message_id


class RotatingClient:
    def __init__(self):
        self.sent = []
        self.deleted = []

    async def send_file(self, chat, file, **kwargs):
        self.sent.append(chat)
        return SentFile(len(self.sent))

    async def delete_messages(self, chat, ids):
        self.deleted.append((chat, list(ids)))


def run_autobackup(module):
    module.db.set("last_auto", 0)
    asyncio.run(module.autobackup())


def test_autobackup_keeps_only_last_n(builtin_loader):
    module = builtin_loader.get_module("backup")
    module.client = RotatingClient()
    module.config["interval"] = "1"
    module.config["keep"] = "2"
    for _ in range(4):
        run_autobackup(module)
    assert module.client.sent == ["me"] * 4
    assert module.client.deleted == [("me", [1]), ("me", [2])]
    assert module.db.get("auto_sent") == [["me", 3], ["me", 4]]


def test_autobackup_keep_zero_deletes_nothing(builtin_loader):
    module = builtin_loader.get_module("backup")
    module.client = RotatingClient()
    module.config["interval"] = "1"
    module.config["keep"] = "0"
    for _ in range(3):
        run_autobackup(module)
    assert module.client.deleted == []


def test_autobackup_rotation_survives_delete_errors(builtin_loader):
    module = builtin_loader.get_module("backup")

    class Client(RotatingClient):
        async def delete_messages(self, chat, ids):
            raise RuntimeError("message is gone")

    module.client = Client()
    module.config["interval"] = "1"
    module.config["keep"] = "1"
    run_autobackup(module)
    run_autobackup(module)
    assert module.db.get("auto_sent") == [["me", 2]]


def test_backup_auto_subcommand(builtin_loader):
    module = builtin_loader.get_module("backup")
    message = FakeMessage(".backup auto 24 7")
    asyncio.run(module.backup_cmd(message))
    assert module.config["interval"] == 24 and module.config["keep"] == 7
    assert "включён" in message.edits[-1] and "токен" in message.edits[-1]

    message = FakeMessage(".backup auto off")
    asyncio.run(module.backup_cmd(message))
    assert module.config["interval"] == 0 and "выключен" in message.edits[-1]

    message = FakeMessage(".backup auto often")
    asyncio.run(module.backup_cmd(message))
    assert module.config["interval"] == 0 and "Не понял" in message.edits[-1]
