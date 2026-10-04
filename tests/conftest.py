import asyncio
import sys

import pytest

from uroboros.database import Database
from uroboros.loader import Loader


class FakeMessage:
    """Своё исходящее сообщение: utils.answer его редактирует."""

    out = True

    def __init__(self, text=""):
        self.raw_text = text
        self.edits = []

    async def edit(self, text, **kwargs):
        self.edits.append(text)
        return self


@pytest.fixture
def builtin_loader(tmp_path):
    db = Database(":memory:")
    loader = Loader(None, db, tmp_path / "modules")
    asyncio.run(loader.load_all())
    yield loader
    db.close()


def builtin_globals(name):
    """Глобальные переменные встроенного модуля (их исполняют через exec, а не импортируют)."""
    return vars(sys.modules[f"uroboros.modules.{name}"])


@pytest.fixture(autouse=True)
def no_github_api(monkeypatch):
    """Тесты не ходят в сеть: SHA коммита не узнать, модули качаются по исходной ссылке."""
    from uroboros import github

    def offline(repo, ref):
        raise OSError("нет сети в тестах")

    monkeypatch.setattr(github, "resolve_commit", offline)
