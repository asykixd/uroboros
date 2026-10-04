"""Обновление из git: каналы ``stable`` (последний тег) и ``beta`` (ветка), список изменений, откат.

Ветки: ``master`` — стабильная, ``dev`` — разработка; ``switch`` переключает между ними.
Установка через pip (без git) обновляется с PyPI: ``check_pip`` / ``install_pip``.

Обновление — только перемотка вперёд (``merge --ff-only``): локальные коммиты и правки не теряются,
а если версия расходится с каналом, обновление отменяется с понятной причиной.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from .errors import LoadError

REPO_DIR = Path(__file__).resolve().parent.parent
CHANNELS = ("stable", "beta")
DEFAULT_CHANNEL = "beta"
MAX_CHANGELOG = 30
TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)(.*)$")
VERSION_RE = re.compile(r'^__version__\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)
BRANCHES = ("master", "dev")
PYPI_URL = "https://pypi.org/pypi/{}/json"
VERSION_KEY_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(.*)$")


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
    await _finish(("reset", "--keep", old))


@dataclass
class Switch:
    branch: str  # куда переходим
    previous: str  # ветка сейчас
    version: str  # версия в целевой ветке
    current_version: str


async def current_branch() -> str:
    branch = await _git_ok("rev-parse", "--abbrev-ref", "HEAD")
    if branch == "HEAD":
        raise UpdateError("Репозиторий не на ветке (detached HEAD): переключитесь вручную, git switch master")
    return branch


async def prepare_switch(branch: str, current_version: str) -> Switch:
    """Проверяет, что на ``branch`` можно перейти, и скачивает её."""
    if branch not in BRANCHES:
        raise UpdateError(f"Ветки: {', '.join(BRANCHES)}")
    previous = await current_branch()
    if previous == branch:
        raise UpdateError(f"Уже стоит ветка {branch}")
    changed = await _git_ok("status", "--porcelain", "--untracked-files=no")
    if changed:
        raise UpdateError(f"В папке бота есть изменённые файлы, переключение их затронет:\n{changed[:500]}")
    await _git_ok("fetch", "--quiet", "origin", branch)
    source = await _git_ok("show", f"origin/{branch}:uroboros/__init__.py")
    match = VERSION_RE.search(source)
    return Switch(branch, previous, match[1] if match else "?", current_version)


async def switch(target: Switch) -> None:
    """Переходит на ветку и ставит зависимости. При ошибке возвращает прежнюю ветку и бросает ``UpdateError``."""
    code, _ = await git("rev-parse", "--verify", "--quiet", f"refs/heads/{target.branch}")
    if code == 0:
        await _git_ok("switch", target.branch)
        code, output = await git("merge", "--ff-only", f"origin/{target.branch}")
        if code != 0:
            await git("switch", target.previous)
            raise UpdateError(f"Локальная ветка {target.branch} расходится с origin: {output[-500:]}")
    else:
        await _git_ok("switch", "--track", "-c", target.branch, f"origin/{target.branch}")
    await _finish(("switch", target.previous))


async def _finish(rollback: tuple[str, ...]) -> None:
    """Ставит зависимости и проверяет, что новая версия импортируется. Нет — ``git <rollback>``."""
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

    rollback, rollback_output = await git(*rollback)
    raise InstallError(stage, output[-2000:], rolled_back=rollback == 0, rollback_output=rollback_output)


# --- установка через pip ---


def distribution() -> str | None:
    """Имя пакета на PyPI, из которого установлен Uroboros (None — не через pip)."""
    try:
        names = importlib.metadata.packages_distributions().get("uroboros") or []
    except Exception:
        return None
    return names[0] if names else None


def is_pip_install() -> bool:
    return not is_git_checkout() and distribution() is not None


def version_key(version: str) -> tuple[int, int, int, int] | None:
    """``1.1.0`` новее ``1.1.0.dev0`` и ``1.1.0-dev``: версия без суффикса — последней."""
    match = VERSION_KEY_RE.match(version.strip())
    if not match:
        return None
    major, minor, patch, suffix = match.groups()
    return int(major), int(minor), int(patch), 0 if suffix else 1


def latest_release(releases: dict[str, list], channel: str) -> str | None:
    """Новейшая версия из ответа PyPI: в канале stable — только без суффиксов, отозванные не считаются."""
    candidates = []
    for version, files in releases.items():
        key = version_key(version)
        if key is None or not files or all(file.get("yanked") for file in files):
            continue
        if channel == "stable" and key[3] == 0:
            continue
        candidates.append((key, version))
    return max(candidates)[1] if candidates else None


def _pypi_releases(dist: str) -> dict[str, list]:
    request = urllib.request.Request(PYPI_URL.format(dist), headers={"User-Agent": "Uroboros"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)["releases"]


async def check_pip(channel: str, current: str) -> Update | None:
    """Есть ли на PyPI версия новее ``current`` в канале ``channel``."""
    if channel not in CHANNELS:
        raise UpdateError(f"Канал — {' или '.join(CHANNELS)}")
    dist = distribution()
    if dist is None:
        raise UpdateError("Uroboros установлен не через pip")
    try:
        releases = await asyncio.to_thread(_pypi_releases, dist)
    except Exception as e:
        raise UpdateError(f"Не удалось узнать версии на PyPI: {e}") from e
    latest = latest_release(releases, channel)
    if latest is None or (version_key(current) or (0, 0, 0, 0)) >= version_key(latest):
        return None
    return Update(target=f"{dist}=={latest}", label=f"PyPI {latest}", sha=latest)


async def install_pip(update: Update, current: str) -> None:
    """Ставит версию с PyPI. Если она не встала или не запускается — возвращает ``current``."""
    dist = update.target.split("==", 1)[0]
    pip = (sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check")
    stage = "Не удалось установить новую версию"
    code, output = await run_process(*pip, update.target)
    if code == 0:
        stage = "Новая версия не запускается"
        code, output = await run_process(sys.executable, "-c", "import uroboros.main")
    if code == 0:
        return
    rollback, rollback_output = await run_process(*pip, f"{dist}=={current}")
    raise InstallError(stage, output[-2000:], rolled_back=rollback == 0, rollback_output=rollback_output)
