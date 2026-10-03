import asyncio
import sys

import pytest
from conftest import FakeMessage, builtin_globals


class FakeProcesses:
    """Подмена git и pip: ответы по первому подходящему префиксу команды."""

    def __init__(self, heads, pip=(0, ""), check=(0, ""), reset=(0, "")):
        self.heads = list(heads)
        self.answers = {"pip": pip, "-c": check, "reset": reset}
        self.calls = []

    async def __call__(self, *args):
        self.calls.append(args)
        if "rev-parse" in args:
            return 0, self.heads.pop(0)
        if "pull" in args:
            return 0, "Fast-forward"
        for marker, answer in self.answers.items():
            if marker in args:
                return answer
        raise AssertionError(args)

    def ran(self, marker):
        return [c for c in self.calls if marker in c]


@pytest.fixture
def system(builtin_loader, monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()
    monkeypatch.setitem(builtin_globals("system"), "REPO_DIR", tmp_path)
    module = builtin_loader.get_module("system")
    module.restarted = False

    async def fake_restart(message):
        module.restarted = True

    module.restart = fake_restart
    return module


def update(system, monkeypatch, processes):
    monkeypatch.setitem(builtin_globals("system"), "run_process", processes)
    message = FakeMessage(".update")
    asyncio.run(system.update(message))
    return message.edits[-1]


def test_already_up_to_date(system, monkeypatch):
    processes = FakeProcesses(["aaa", "aaa"])
    assert update(system, monkeypatch, processes) == "✅ Установлена последняя версия"
    assert not processes.ran("pip") and not system.restarted


def test_pip_failure_rolls_back(system, monkeypatch):
    processes = FakeProcesses(["aaa", "bbb"], pip=(1, "error: can't find Rust compiler"))
    text = update(system, monkeypatch, processes)
    assert "Не удалось установить зависимости" in text and "Rust compiler" in text
    assert "Вернул прежнюю версию" in text
    assert processes.ran("reset")[0][-2:] == ("--keep", "aaa")
    assert not processes.ran("-c") and not system.restarted


def test_broken_new_version_rolls_back(system, monkeypatch):
    processes = FakeProcesses(["aaa", "bbb"], check=(1, "ModuleNotFoundError: No module named 'aiogram'"))
    text = update(system, monkeypatch, processes)
    assert "Новая версия не запускается" in text and "aiogram" in text
    assert processes.ran("-c")[0][:2] == (sys.executable, "-c")
    assert not system.restarted


def test_failed_rollback_is_reported(system, monkeypatch):
    processes = FakeProcesses(["aaa", "bbb"], pip=(1, "boom"), reset=(1, "local changes"))
    text = update(system, monkeypatch, processes)
    assert "Не удалось вернуть прежнюю версию" in text and "local changes" in text
    assert not system.restarted


def test_successful_update_restarts(system, monkeypatch):
    processes = FakeProcesses(["aaa", "bbb"])
    update(system, monkeypatch, processes)
    assert system.restarted and not processes.ran("reset")
