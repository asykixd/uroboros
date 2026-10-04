"""`.dev on/off`: переключение между ветками master и dev на настоящем git (локальный origin, без сети)."""

import asyncio
import shutil
import subprocess

import pytest
from conftest import FakeMessage

from uroboros import updater

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="нужен git")
CHECKS = {}  # ответы pip и проверки импорта


def sh(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout.strip()


def commit_version(repo, version):
    (repo / "uroboros").mkdir(exist_ok=True)
    (repo / "uroboros" / "__init__.py").write_text(f'__version__ = "{version}"\n')
    sh(repo, "add", "-A")
    sh(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", version)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """origin с ветками master (1.0.0) и dev (1.1.0-dev) и клон на master — папка бота."""
    origin = tmp_path / "origin"
    origin.mkdir()
    sh(origin, "init", "-q", "-b", "master")
    commit_version(origin, "1.0.0")
    sh(origin, "switch", "-qc", "dev")
    commit_version(origin, "1.1.0-dev")
    sh(origin, "switch", "-q", "master")

    clone = tmp_path / "bot"
    subprocess.run(["git", "clone", "-q", str(origin), str(clone)], check=True)
    monkeypatch.setattr(updater, "REPO_DIR", clone)

    real = updater.run_process
    CHECKS.clear()
    CHECKS.update({"pip": (0, ""), "-c": (0, "")})

    async def fake_run(*args):
        if args[0] == "git":
            return await real(*args)
        return next(answer for marker, answer in CHECKS.items() if marker in args)

    monkeypatch.setattr(updater, "run_process", fake_run)
    return clone


def version(repo):
    return (repo / "uroboros" / "__init__.py").read_text().split('"')[1]


def test_switch_to_dev_and_back(repo):
    target = asyncio.run(updater.prepare_switch("dev", "1.0.0"))
    assert (target.previous, target.version) == ("master", "1.1.0-dev")
    asyncio.run(updater.switch(target))
    assert sh(repo, "rev-parse", "--abbrev-ref", "HEAD") == "dev" and version(repo) == "1.1.0-dev"

    target = asyncio.run(updater.prepare_switch("master", "1.1.0-dev"))
    asyncio.run(updater.switch(target))
    assert sh(repo, "rev-parse", "--abbrev-ref", "HEAD") == "master" and version(repo) == "1.0.0"

    # Локальная dev уже есть — переключение перематывает её на origin/dev.
    asyncio.run(updater.switch(asyncio.run(updater.prepare_switch("dev", "1.0.0"))))
    assert version(repo) == "1.1.0-dev"


def test_broken_branch_rolls_back(repo):
    CHECKS["-c"] = (1, "ImportError: boom")
    target = asyncio.run(updater.prepare_switch("dev", "1.0.0"))
    with pytest.raises(updater.InstallError) as error:
        asyncio.run(updater.switch(target))
    assert error.value.rolled_back and "boom" in error.value.output
    assert sh(repo, "rev-parse", "--abbrev-ref", "HEAD") == "master" and version(repo) == "1.0.0"


def test_refuses_same_branch_and_local_changes(repo):
    with pytest.raises(updater.UpdateError, match="Уже стоит ветка master"):
        asyncio.run(updater.prepare_switch("master", "1.0.0"))
    (repo / "uroboros" / "__init__.py").write_text("правка\n")
    with pytest.raises(updater.UpdateError, match="изменённые файлы"):
        asyncio.run(updater.prepare_switch("dev", "1.0.0"))


@pytest.fixture
def system(builtin_loader, repo, monkeypatch):
    monkeypatch.setattr(updater, "is_git_checkout", lambda: True)
    monkeypatch.delenv("UROBOROS_DOCKER", raising=False)
    module = builtin_loader.get_module("system")
    module.restarted = False

    async def fake_restart(message):
        module.restarted = True

    module.restart = fake_restart
    return module


def run(system, text):
    message = FakeMessage(text)
    asyncio.run(system.dev(message))
    return message.edits[-1]


def test_dev_command(system, repo):
    assert "🌿 <b>Ветка</b> <code>master</code>" in run(system, ".dev") and "dev on" in run(system, ".dev")

    text = run(system, ".dev on")
    assert "Перейти на сборку из ветки dev?" in text and "1.1.0-dev" in text and "dev on -f" in text
    assert not system.restarted and sh(repo, "rev-parse", "--abbrev-ref", "HEAD") == "master"

    system.db.set("channel", "stable")
    run(system, ".dev on -f")
    assert system.restarted and sh(repo, "rev-parse", "--abbrev-ref", "HEAD") == "dev"
    assert system.db.get("channel") == "beta"

    system.restarted = False
    run(system, ".dev off -f")
    assert system.restarted and sh(repo, "rev-parse", "--abbrev-ref", "HEAD") == "master"


def test_dev_command_reports_errors(system, repo):
    # UpdateError — LoadError: диспетчер покажет его текст с ❌.
    with pytest.raises(updater.UpdateError, match="Уже стоит ветка master"):
        run(system, ".dev off")
    assert run(system, ".dev nope").startswith("❌")
