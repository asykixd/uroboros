"""Health check after ``.update`` / ``.dev``: a version that doesn't come up is rolled back.

Before restarting into a new version the old one writes ``update-pending.json`` with how to return
(``arm``). Each start counts an attempt (``begin``); reaching "ready" clears the marker (``confirm``).
``main`` rolls back when startup raises during that trial, or when the marker shows the trial already
failed ``MAX_ATTEMPTS`` times without raising (a hard crash under systemd, a killed process). The rollback runs
in the new process: its import was checked before the restart, so only later failures are left for here.

The marker holds structured data, never commands: a module able to write files must not get a way to run
arbitrary programs at the next start.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from . import updater

log = logging.getLogger(__name__)

MARKER = "update-pending.json"
NOTICE = "update-rolled-back.json"
MAX_ATTEMPTS = 2
STEP_TIMEOUT = 900
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_PIN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*==[A-Za-z0-9][A-Za-z0-9.+!-]*$")


class UnhealthyError(RuntimeError):
    """The new version started, but without what it needs to work (and to update again)."""


@dataclass
class Pending:
    rollback: updater.Rollback
    previous: str  # version to return to
    target: str  # what was installed, as shown to the user
    attempts: int = 0


def _valid(rollback: updater.Rollback) -> bool:
    if rollback.kind == "git":
        return bool(_SHA_RE.match(rollback.ref)) or rollback.ref in updater.BRANCHES
    if rollback.kind == "pip":
        return bool(_PIN_RE.match(rollback.ref) or updater.ARCHIVE_RE.match(rollback.ref))
    return False


def _write(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    os.replace(tmp, path)


def arm(data_dir: Path, rollback: updater.Rollback, previous: str, target: str) -> None:
    """Called right before restarting into a freshly installed version."""
    if not _valid(rollback):
        raise ValueError(f"Bad rollback target: {rollback}")
    data = {"kind": rollback.kind, "ref": rollback.ref, "previous": previous, "target": target, "attempts": 0}
    _write(Path(data_dir) / MARKER, data)


def _read(data_dir: Path) -> Pending | None:
    path = Path(data_dir) / MARKER
    try:
        data = json.loads(path.read_text("utf-8"))
        pending = Pending(
            updater.Rollback(str(data["kind"]), str(data["ref"])),
            str(data["previous"]),
            str(data["target"]),
            int(data["attempts"]),
        )
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError):
        log.warning("Повреждён %s, проверка обновления пропущена", path)
        path.unlink(missing_ok=True)
        return None
    if not _valid(pending.rollback):
        log.warning("В %s неверная цель отката, проверка обновления пропущена", path)
        path.unlink(missing_ok=True)
        return None
    return pending


def begin(data_dir: Path) -> Pending | None:
    """At startup: the pending update, with this start counted, or None if nothing is being checked."""
    pending = _read(data_dir)
    if pending is None:
        return None
    pending.attempts += 1
    data = {
        "kind": pending.rollback.kind,
        "ref": pending.rollback.ref,
        "previous": pending.previous,
        "target": pending.target,
        "attempts": pending.attempts,
    }
    _write(Path(data_dir) / MARKER, data)
    return pending


def is_pending(data_dir: Path) -> bool:
    return (Path(data_dir) / MARKER).exists()


def confirm(data_dir: Path, *, healthy: bool) -> None:
    """The bot is ready: the new version is kept. ``healthy=False`` during a trial raises ``UnhealthyError``."""
    if not is_pending(data_dir):
        return
    if not healthy:
        raise UnhealthyError("Встроенный модуль System не загрузился: без него бот не сможет обновиться снова")
    (Path(data_dir) / MARKER).unlink(missing_ok=True)
    log.info("Новая версия запустилась, обновление сохранено")


def rollback_steps(rollback: updater.Rollback) -> list[tuple[str, ...]]:
    if rollback.kind == "git":
        repo = str(updater.REPO_DIR)
        back = ("reset", "--keep", rollback.ref) if _SHA_RE.match(rollback.ref) else ("switch", rollback.ref)
        pip = (sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "-e", repo)
        return [("git", "-C", repo, *back), pip]
    return updater._pip_steps(rollback.ref)


def _run(step: tuple[str, ...]) -> tuple[int, str]:
    try:
        result = subprocess.run(
            step,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            timeout=STEP_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)
    return result.returncode, result.stdout.decode(errors="replace").strip()


def rollback(data_dir: Path, pending: Pending, reason: str) -> bool:
    """Returns the previous version and leaves a notice for the next start. True if it went back."""
    log.error("Новая версия (%s) не запустилась: %s. Откатываю на %s", pending.target, reason, pending.previous)
    code, output = 0, ""
    for step in rollback_steps(pending.rollback):
        code, output = _run(step)
        if code != 0:
            break
    ok = code == 0
    if ok:
        log.info("Откат на %s выполнен", pending.previous)
    else:
        log.critical("Откат не удался, верните версию вручную:\n%s", output[-2000:])
    (Path(data_dir) / MARKER).unlink(missing_ok=True)
    notice = {
        "previous": pending.previous,
        "target": pending.target,
        "reason": reason[-2000:],
        "ok": ok,
        "output": "" if ok else output[-2000:],
        "time": int(time.time()),
    }
    _write(Path(data_dir) / NOTICE, notice)
    return ok


def take_notice(data_dir: Path) -> dict | None:
    """The last rollback report, once: the file is removed after reading."""
    path = Path(data_dir) / NOTICE
    try:
        data = json.loads(path.read_text("utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        data = None
    path.unlink(missing_ok=True)
    return data if isinstance(data, dict) else None
