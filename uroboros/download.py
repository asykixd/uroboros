"""Скачивание исходников модулей и библиотек."""

from __future__ import annotations

import asyncio
import urllib.error
import urllib.request

from .errors import LoadError

MAX_SIZE = 2 * 1024 * 1024


class _HttpsOnlyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.startswith("https://"):
            raise LoadError(f"Перенаправление не на https: {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_HttpsOnlyRedirect)


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Uroboros"})
    with _opener.open(request, timeout=30) as response:
        data = response.read(MAX_SIZE + 1)
    if len(data) > MAX_SIZE:
        raise LoadError("Файл больше 2 МБ")
    return data


async def download(url: str) -> bytes:
    """Скачивает файл. Только https: по http модуль можно подменить по дороге."""
    if not url.startswith("https://"):
        raise LoadError(f"Модули скачиваются только по https: {url}")
    try:
        return await asyncio.to_thread(_fetch, url)
    except LoadError:
        raise
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise LoadError(f"Не найдено: {url}") from e
        raise LoadError(f"Не удалось скачать {url}: HTTP {e.code}") from e
    except Exception as e:
        raise LoadError(f"Не удалось скачать {url}: {e}") from e


def decode(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise LoadError("Файл не в UTF-8") from None


async def download_source(url: str) -> str:
    return decode(await download(url))
