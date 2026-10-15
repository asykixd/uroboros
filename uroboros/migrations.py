"""DB schema version (``uroboros.main``/``schema``) and the migrations that bring an older DB up to date.

``MIGRATIONS[i]`` upgrades a DB from version ``i`` to ``i + 1``. A migration only appends: never edit or
reorder existing ones, since released DBs have already run them. Migrations run at startup, so a DB restored
from an older backup is upgraded on the restart that follows ``.restore``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from .database import MAIN_OWNER, Database

log = logging.getLogger(__name__)

SCHEMA_KEY = "schema"


def _baseline(db: Database) -> None:
    """Version 1: the layout as of 1.1.0; DBs from before schema versioning need no changes."""


MIGRATIONS: list[Callable[[Database], None]] = [_baseline]
LATEST = len(MIGRATIONS)


def version(db: Database) -> int:
    """Schema version of ``db``; a non-empty DB without the key predates versioning (0)."""
    value = db.get(MAIN_OWNER, SCHEMA_KEY)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def dump_version(dump: dict[str, dict]) -> int:
    """Same as ``version`` for a backup's ``db.json``."""
    value = dump.get(MAIN_OWNER, {}).get(SCHEMA_KEY)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def migrate(db: Database) -> int:
    """Runs pending migrations in order and returns the resulting version.

    A fresh (empty) DB starts at ``LATEST``. A DB from a newer Uroboros is left untouched: downgrading isn't
    supported, but the bot should still start.
    """
    if not db.dump():
        db.set(MAIN_OWNER, SCHEMA_KEY, LATEST)
        return LATEST
    current = version(db)
    if current > LATEST:
        log.warning("БД от более новой версии Uroboros (схема %d, эта версия знает до %d)", current, LATEST)
        return current
    for index in range(current, LATEST):
        log.info("Миграция БД: схема %d → %d", index, index + 1)
        MIGRATIONS[index](db)
        # After each step, so a crash mid-way resumes from the failed migration rather than the start.
        db.set(MAIN_OWNER, SCHEMA_KEY, index + 1)
    return LATEST
