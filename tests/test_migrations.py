import pytest

from uroboros import backup, migrations
from uroboros.database import MAIN_OWNER, Database


@pytest.fixture
def db():
    database = Database(":memory:")
    yield database
    database.close()


def test_fresh_db_gets_latest_version(db):
    assert migrations.migrate(db) == migrations.LATEST
    assert db.get(MAIN_OWNER, migrations.SCHEMA_KEY) == migrations.LATEST


def test_old_db_runs_migrations_in_order(db, monkeypatch):
    calls = []
    steps = [lambda d: calls.append(1), lambda d: calls.append(2), lambda d: calls.append(3)]
    monkeypatch.setattr(migrations, "MIGRATIONS", steps)
    monkeypatch.setattr(migrations, "LATEST", 3)
    db.set(MAIN_OWNER, "prefix", "!")  # an existing DB from before versioning
    db.set(MAIN_OWNER, migrations.SCHEMA_KEY, 1)
    assert migrations.migrate(db) == 3
    assert calls == [2, 3]
    assert db.get(MAIN_OWNER, migrations.SCHEMA_KEY) == 3
    migrations.migrate(db)
    assert calls == [2, 3]


def test_unversioned_db_starts_from_zero(db, monkeypatch):
    calls = []
    monkeypatch.setattr(migrations, "MIGRATIONS", [lambda d: calls.append(d.get(MAIN_OWNER, "prefix"))])
    monkeypatch.setattr(migrations, "LATEST", 1)
    db.set(MAIN_OWNER, "prefix", "!")
    migrations.migrate(db)
    assert calls == ["!"]


def test_failed_migration_resumes_from_where_it_stopped(db, monkeypatch):
    def broken(d):
        raise RuntimeError("boom")

    monkeypatch.setattr(migrations, "MIGRATIONS", [lambda d: None, broken])
    monkeypatch.setattr(migrations, "LATEST", 2)
    db.set(MAIN_OWNER, "prefix", "!")
    with pytest.raises(RuntimeError):
        migrations.migrate(db)
    assert db.get(MAIN_OWNER, migrations.SCHEMA_KEY) == 1


def test_newer_db_is_left_alone(db):
    db.set(MAIN_OWNER, migrations.SCHEMA_KEY, migrations.LATEST + 5)
    assert migrations.migrate(db) == migrations.LATEST + 5
    assert db.get(MAIN_OWNER, migrations.SCHEMA_KEY) == migrations.LATEST + 5


def test_restored_old_backup_is_migrated(db, tmp_path, monkeypatch):
    source = Database(":memory:")
    source.set(MAIN_OWNER, "prefix", "!")  # backup from before schema versioning
    data = backup.create(source, tmp_path / "src")
    source.close()

    calls = []
    monkeypatch.setattr(migrations, "MIGRATIONS", [lambda d: calls.append("v1"), lambda d: calls.append("v2")])
    monkeypatch.setattr(migrations, "LATEST", 2)
    migrations.migrate(db)
    backup.restore(data, db, tmp_path / "modules")

    # After .restore the bot restarts: a new Database on the same file, migrated at startup.
    restored = Database(":memory:")
    restored.replace_all(db.dump())
    assert migrations.version(restored) == 0
    migrations.migrate(restored)
    assert calls == ["v1", "v2"]
    assert migrations.version(restored) == 2
    restored.close()


def test_backup_from_newer_schema_is_rejected(tmp_path):
    source = Database(":memory:")
    source.set(MAIN_OWNER, migrations.SCHEMA_KEY, migrations.LATEST + 1)
    data = backup.create(source, tmp_path)
    source.close()
    with pytest.raises(backup.BackupError, match="более новой"):
        backup.parse(data)
