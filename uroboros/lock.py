"""Защита от второго экземпляра с той же папкой данных (и той же сессией)."""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
from typing import IO


class InstanceLock:
    """Эксклюзивная блокировка файла ``uroboros.lock``.

    Блокировку держит открытый файл, поэтому она снимается и при падении процесса,
    и при ``os.execv`` (дескриптор не наследуется).
    """

    def __init__(self, path: Path):
        self.path = path
        self._file: IO[str] | None = None

    def acquire(self) -> bool:
        file = open(self.path, "a+", encoding="utf-8")  # noqa: SIM115 — файл живёт, пока держим блокировку
        try:
            _lock(file)
        except OSError:
            file.close()
            return False
        file.seek(0)
        file.truncate()
        file.write(str(os.getpid()))
        file.flush()
        self._file = file
        return True

    def release(self) -> None:
        if self._file is None:
            return
        with contextlib.suppress(OSError):
            _unlock(self._file)
        self._file.close()
        self._file = None

    def owner_pid(self) -> str | None:
        """PID процесса, который держит блокировку, если его можно прочитать."""
        try:
            return self.path.read_text("utf-8").strip() or None
        except OSError:
            return None


if os.name == "nt":
    import msvcrt

    def _lock(file: IO[str]) -> None:
        file.seek(0)
        msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(file: IO[str]) -> None:
        file.seek(0)
        msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock(file: IO[str]) -> None:
        fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(file: IO[str]) -> None:
        fcntl.flock(file.fileno(), fcntl.LOCK_UN)
