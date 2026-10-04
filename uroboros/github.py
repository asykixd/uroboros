"""Разбор ссылок на GitHub: модули и репозитории модулей."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import urllib.request

log = logging.getLogger(__name__)

RAW = "https://raw.githubusercontent.com"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_NAME = r"[A-Za-z0-9_.-]+"

_REPO_URL_RE = re.compile(rf"^(?:https?://)?(?:www\.)?github\.com/({_NAME})/({_NAME}?)(?:\.git)?/?$")
_REPO_SHORT_RE = re.compile(rf"^({_NAME})/({_NAME})$")
_FILE_URL_RE = re.compile(rf"^(?:https?://)?(?:www\.)?github\.com/({_NAME})/({_NAME})/(?:blob|raw)/([^/]+)/(.+)$")
_FILE_SHORT_RE = re.compile(rf"^({_NAME})/({_NAME})/(.+)$")


def parse_repo(spec: str) -> str | None:
    """``owner/repo`` или ``https://github.com/owner/repo`` → ``owner/repo``."""
    spec = spec.strip()
    match = _REPO_URL_RE.match(spec) or _REPO_SHORT_RE.match(spec)
    return f"{match[1]}/{match[2]}" if match else None


def to_raw_url(spec: str) -> str | None:
    """Ссылка или короткий путь к файлу на GitHub → прямая ссылка на содержимое.

    Поддерживается:
      https://github.com/owner/repo/blob/main/path/mod.py
      https://raw.githubusercontent.com/owner/repo/main/mod.py (как есть)
      owner/repo/path/mod  (ветка по умолчанию, .py можно не писать)
    """
    spec = spec.strip()
    if spec.startswith(RAW + "/"):
        return spec
    if match := _FILE_URL_RE.match(spec):
        owner, repo, ref, path = match.groups()
        return f"{RAW}/{owner}/{repo}/{ref}/{path}"
    if not spec.startswith(("http://", "https://")) and (match := _FILE_SHORT_RE.match(spec)):
        owner, repo, path = match.groups()
        if not path.endswith(".py"):
            path += ".py"
        return f"{RAW}/{owner}/{repo}/HEAD/{path}"
    return None


def repo_of(url: str) -> str | None:
    """Из какого репозитория прямая ссылка: ``https://raw.githubusercontent.com/o/r/...`` → ``o/r``."""
    if not url.startswith(RAW + "/"):
        return None
    parts = url[len(RAW) + 1 :].split("/")
    return f"{parts[0]}/{parts[1]}" if len(parts) > 2 else None


def split_raw(url: str) -> tuple[str, str, str] | None:
    """``https://raw.githubusercontent.com/o/r/ref/path`` → ``("o/r", "ref", "path")``."""
    if not url.startswith(RAW + "/"):
        return None
    parts = url[len(RAW) + 1 :].split("/", 3)
    if len(parts) < 4 or not all(parts):
        return None
    return f"{parts[0]}/{parts[1]}", parts[2], parts[3]


def resolve_commit(repo: str, ref: str) -> str:
    """SHA коммита, на который сейчас указывает ветка или ``HEAD`` (синхронно, вызывать через to_thread)."""
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/commits/{ref}",
        headers={"User-Agent": "Uroboros", "Accept": "application/vnd.github.sha"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        sha = response.read(100).decode().strip()
    if not SHA_RE.match(sha):
        raise ValueError(f"GitHub вернул не SHA: {sha[:50]}")
    return sha


async def pin(url: str) -> tuple[str, str] | None:
    """Прямая ссылка на GitHub → (ссылка на тот же файл в конкретном коммите, SHA).

    Содержимое по такой ссылке не меняется. None — ссылка не на GitHub или GitHub API недоступен
    (например, кончился лимит запросов): тогда модуль качается по исходной ссылке.
    """
    parts = split_raw(url)
    if parts is None:
        return None
    repo, ref, path = parts
    if SHA_RE.match(ref):
        return url, ref
    try:
        sha = await asyncio.to_thread(resolve_commit, repo, ref)
    except Exception as e:
        log.warning("Не удалось узнать коммит %s@%s: %s", repo, ref, e)
        return None
    return f"{RAW}/{repo}/{sha}/{path}", sha


def commit_link(pinned_url: str) -> str | None:
    """Ссылка на коммит для показа пользователю."""
    parts = split_raw(pinned_url)
    if parts is None or not SHA_RE.match(parts[1]):
        return None
    return f"https://github.com/{parts[0]}/commit/{parts[1]}"


def module_url(repo: str, name: str) -> str:
    name = name if name.endswith(".py") else f"{name}.py"
    return f"{RAW}/{repo}/HEAD/{name}"


def list_modules(repo: str) -> list[str]:
    """Имена .py-файлов в корне репозитория (синхронно, вызывать через to_thread)."""
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/contents/",
        headers={"User-Agent": "Uroboros", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        items = json.load(response)
    return sorted(
        item["name"].removesuffix(".py")
        for item in items
        if item.get("type") == "file" and item["name"].endswith(".py") and not item["name"].startswith("_")
    )
