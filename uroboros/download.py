"""Скачивание исходников модулей и библиотек."""

from __future__ import annotations

import asyncio
import urllib.error
import urllib.request

from .errors import LoadError

MAX_SIZE = 2 * 1024 * 1024


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Uroboros"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(MAX_SIZE + 1)
    if len(data) > MAX_SIZE:
        raise LoadError("Файл больше 2 МБ")
    return data


async def download(url: str) -> bytes:
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
