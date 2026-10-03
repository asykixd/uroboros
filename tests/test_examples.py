"""Примеры из examples/ должны загружаться: так документация не устаревает молча."""

import asyncio
from pathlib import Path

import pytest

from uroboros import download
from uroboros.database import Database
from uroboros.loader import Loader

EXAMPLES = Path(__file__).parent.parent / "examples"


# textlib.py — библиотека, она проверяется через shout.py.
@pytest.mark.parametrize("path", sorted(p for p in EXAMPLES.glob("*.py") if p.stem != "textlib"), ids=lambda p: p.stem)
def test_example_loads(path, tmp_path, monkeypatch):
    async def fake_download(url):
        return (EXAMPLES / url.rsplit("/", 1)[-1]).read_bytes()

    monkeypatch.setattr(download, "download", fake_download)

    async def scenario():
        loader = Loader(None, Database(":memory:"), tmp_path)
        (inst,) = await loader.install(path.read_text("utf-8"), f"file:{path.name}")
        assert loader.module_commands(inst)
        await loader.unload_all()

    asyncio.run(scenario())
