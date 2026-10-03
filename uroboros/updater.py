"""Обновление из git: каналы ``stable`` (последний тег) и ``beta`` (ветка), список изменений, откат.

Обновление — только перемотка вперёд (``merge --ff-only``): локальные коммиты и правки не теряются,
а если версия расходится с каналом, обновление отменяется с понятной причиной.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .errors import LoadError

REPO_DIR = Path(__file__).resolve().parent.parent
CHANNELS = ("stable", "beta")
DEFAULT_CHANNEL = "beta"
MAX_CHANGELOG = 30
TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)(.*)$")


class UpdateError(LoadError):
    """Обновиться нельзя; текст показывается пользователю."""


class InstallError(UpdateError):
    """Новая версия не встала. ``rolled_back`` — вернулась ли прежняя."""

    def __init__(self, stage: str, output: str, *, rolled_back: bool, rollback_output: str = ""):
        super().__init__(f"{stage}:\n{output}")
        self.stage = stage
        self.output = output
        self.rolled_back = rolled_back
        self.rollback_output = rollback_output


@dataclass
class Update:
    target: str  # что ставим: origin/<ветка> или тег
    label: str  # как показать пользователю
    sha: str
    commits: list[str] = field(default_factory=list)  # «хеш сообщение», новые сверху


def in_docker() -> bool:
    return bool(os.environ.get("UROBOROS_DOCKER"))


def is_git_checkout() -> bool:
    return (REPO_DIR / ".git").exists()


async def run_process(*args: str) -> tuple[int, str]:
    """Запускает процесс и возвращает код выхода и весь вывод."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},  # git не должен ждать логин в консоли
    )
    output, _ = await proc.communicate()
    return proc.returncode, output.decode(errors="replace").strip()


async def git(*args: str) -> tuple[int, str]:
    return await run_process("git", "-C", str(REPO_DIR), *args)


async def _git_ok(*args: str) -> str:
    code, output = await git(*args)
    if code != 0:
        raise UpdateError(f"git {' '.join(args)}: {output[-500:]}")
    return output


def tag_key(tag: str) -> tuple[int, int, int, int] | None:
    """``v0.3.0`` новее ``v0.3.0-dev`` и ``v0.3.0b1``: релиз без суффикса — последним."""
    match = TAG_RE.match(tag)
    if not match:
        return None
    major, minor, patch, suffix = match.groups()
    return int(major), int(minor), int(patch), 0 if suffix else 1


def latest_tag(tags: list[str]) -> str | None:
    keyed = [(tag_key(tag), tag) for tag in tags if tag_key(tag) is not None]
    return max(keyed)[1] if keyed else None


async def check(channel: str) -> Update | None:
    """Скачивает новости канала. Есть что ставить — ``Update``, нет — None."""
    if channel not in CHANNELS:
        raise UpdateError(f"Канал — {' или '.join(CHANNELS)}")
    await _git_ok("fetch", "--tags", "--quiet", "origin")
    if channel == "beta":
        branch = await _git_ok("rev-parse", "--abbrev-ref", "HEAD")
        if branch == "HEAD":
            raise UpdateError("Репозиторий не на ветке (detached HEAD): переключитесь на master")
        target = label = f"origin/{branch}"
    else:
        tag = latest_tag((await _git_ok("tag", "--list", "v*")).split())
        if tag is None:
            raise UpdateError("В канале stable ещё нет релизов")
        target = label = tag

    head = await _git_ok("rev-parse", "HEAD")
    sha = await _git_ok("rev-parse", f"{target}^{{commit}}")
    if head == sha:
        return None
    code, _ = await git("merge-base", "--is-ancestor", "HEAD", sha)
    if code != 0:
        code, _ = await git("merge-base", "--is-ancestor", sha, "HEAD")
        if code == 0:
            return None  # стоит версия новее канала (например, переключились с beta на stable)
        raise UpdateError(f"Локальная версия расходится с {label}: обновите вручную (git status, git pull)")
    log = await _git_ok("log", "--oneline", "--no-decorate", f"-{MAX_CHANGELOG + 1}", f"HEAD..{sha}")
    return Update(target=target, label=label, sha=sha, commits=[line for line in log.splitlines() if line])


async def install(update: Update) -> None:
    """Перематывает на ``update`` и ставит зависимости. При ошибке откатывает git и бросает ``UpdateError``."""
    old = await _git_ok("rev-parse", "HEAD")
    code, output = await git("merge", "--ff-only", update.sha)
    if code != 0:
        raise UpdateError(f"Не удалось обновиться: {output[-500:]}")

    # Новые зависимости ставятся до рестарта: если не встанут, бот после рестарта не запустится.
    stage = "Не удалось установить зависимости"
    code, output = await run_process(
        sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "-e", str(REPO_DIR)
    )
    if code == 0:
        stage = "Новая версия не запускается"
        code, output = await run_process(sys.executable, "-c", "import uroboros.main")
    if code == 0:
        return

    rollback, rollback_output = await git("reset", "--keep", old)
    raise InstallError(stage, output[-2000:], rolled_back=rollback == 0, rollback_output=rollback_output)
