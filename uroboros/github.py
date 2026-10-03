"""Разбор ссылок на GitHub: модули и репозитории модулей."""

from __future__ import annotations

import json
import re
import urllib.request

RAW = "https://raw.githubusercontent.com"
_NAME = r"[A-Za-z0-9_.-]+"

_REPO_URL_RE = re.compile(rf"^(?:https?://)?(?:www\.)?github\.com/({_NAME})/({_NAME}?)(?:\.git)?/?$")
_REPO_SHORT_RE = re.compile(rf"^({_NAME})/({_NAME})$")
_FILE_URL_RE = re.compile(
    rf"^(?:https?://)?(?:www\.)?github\.com/({_NAME})/({_NAME})/(?:blob|raw)/([^/]+)/(.+)$"
)
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
        if item.get("type") == "file"
        and item["name"].endswith(".py")
        and not item["name"].startswith("_")
    )
