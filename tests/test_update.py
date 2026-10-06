import asyncio
import sys

import pytest
from conftest import FakeMessage
from fake_inline import FakeMessage as InlineMessage
from fake_inline import make_env, press

from uroboros import updater


class FakeGit:
    """Подмена git и pip: HEAD → target по шагам, ответы задаются в тесте."""

    def __init__(self, *, head="aaa", target="bbb", tags="", pip=(0, ""), check=(0, ""), reset=(0, ""), diverged=False):
        self.head, self.target, self.tags = head, target, tags
        self.answers = {"pip": pip, "-c": check}
        self.reset = reset
        self.diverged = diverged
        self.calls = []

    async def __call__(self, *args):
        self.calls.append(args)
        if args[0] == "git":
            return self.git(args[3:])
        for marker, answer in self.answers.items():
            if marker in args:
                return answer
        raise AssertionError(args)

    def git(self, args):
        cmd = args[0]
        if cmd == "fetch":
            return 0, ""
        if cmd == "rev-parse":
            if args[1] == "--abbrev-ref":
                return 0, "master"
            return 0, self.head if args[1] == "HEAD" else self.target
        if cmd == "tag":
            return 0, self.tags
        if cmd == "merge-base":
            return (1, "") if self.diverged else (0, "")
        if cmd == "log":
            return 0, "bbb2 Вторая правка\nbbb1 Первая правка"
        if cmd == "merge":
            self.head = self.target
            return 0, "Fast-forward"
        if cmd == "reset":
            return self.reset
        raise AssertionError(args)

    def ran(self, marker):
        return [c for c in self.calls if marker in c]


@pytest.fixture
def system(builtin_loader, monkeypatch):
    monkeypatch.setattr(updater, "is_git_checkout", lambda: True)
    monkeypatch.delenv("UROBOROS_DOCKER", raising=False)
    module = builtin_loader.get_module("system")
    module.restarted = False

    async def fake_restart(message):
        module.restarted = True

    module.restart = fake_restart
    return module


def update(system, monkeypatch, fake, text=".update -f"):
    monkeypatch.setattr(updater, "run_process", fake)
    message = FakeMessage(text)
    asyncio.run(system.update(message))
    return message.edits[-1]


def test_already_up_to_date(system, monkeypatch):
    fake = FakeGit(head="aaa", target="aaa")
    assert update(system, monkeypatch, fake).startswith("✅ <b>Установлена последняя версия")
    assert not fake.ran("pip") and not system.restarted


def test_changelog_without_force(system, monkeypatch):
    fake = FakeGit()
    text = update(system, monkeypatch, fake, ".update")
    assert "Доступно обновление" in text and "Первая правка" in text and "update -f" in text
    assert not fake.ran("merge") and not system.restarted


def test_pip_failure_rolls_back(system, monkeypatch):
    fake = FakeGit(pip=(1, "error: can't find Rust compiler"))
    text = update(system, monkeypatch, fake)
    assert "Не удалось установить зависимости" in text and "Rust compiler" in text
    assert "Вернул прежнюю версию" in text
    reset = next(c for c in fake.calls if "reset" in c)
    assert reset[-2:] == ("--keep", "aaa")
    assert not fake.ran("-c") and not system.restarted


def test_broken_new_version_rolls_back(system, monkeypatch):
    fake = FakeGit(check=(1, "ModuleNotFoundError: No module named 'aiogram'"))
    text = update(system, monkeypatch, fake)
    assert "Новая версия не запускается" in text and "aiogram" in text
    assert fake.ran("-c")[0][:2] == (sys.executable, "-c")
    assert not system.restarted


def test_failed_rollback_is_reported(system, monkeypatch):
    fake = FakeGit(pip=(1, "boom"), reset=(1, "local changes"))
    text = update(system, monkeypatch, fake)
    assert "Не удалось вернуть прежнюю версию" in text and "local changes" in text
    assert not system.restarted


def test_successful_update_restarts(system, monkeypatch):
    fake = FakeGit()
    update(system, monkeypatch, fake)
    assert system.restarted and fake.ran("merge")[0][-2:] == ("--ff-only", "bbb")


def test_diverged_is_reported(system, monkeypatch):
    fake = FakeGit(diverged=True)
    with pytest.raises(updater.UpdateError, match="расходится"):
        update(system, monkeypatch, fake)


def test_stable_channel_uses_latest_tag(system, monkeypatch):
    run = lambda text: update(system, monkeypatch, fake, text)  # noqa: E731
    fake = FakeGit(tags="v0.1.0b1 v0.3.0-dev v0.10.0-dev v0.3.0 junk")
    assert "stable" in run(".update channel stable")
    assert "v0.10.0-dev" in run(".update")
    assert "❌" in run(".update channel nightly")


def test_tag_order():
    assert updater.latest_tag(["v0.3.0", "v0.3.0-dev", "v0.2.9"]) == "v0.3.0"
    assert updater.latest_tag(["v1.0.0-dev", "v0.9.9"]) == "v1.0.0-dev"
    assert updater.latest_tag(["nope"]) is None


def test_docker_refuses(system, monkeypatch):
    monkeypatch.setenv("UROBOROS_DOCKER", "1")
    assert "docker compose" in update(system, monkeypatch, FakeGit(), ".update")


def test_notify_toggle(system, monkeypatch):
    assert "выключены" in update(system, monkeypatch, FakeGit(), ".update notify off")
    assert system.db.get("notify") is False


def test_daily_notification(system, monkeypatch):
    sent = []

    class Client:
        async def send_message(self, chat, text, **kwargs):
            sent.append((chat, text))

    system.client = Client()
    monkeypatch.setattr(updater, "run_process", FakeGit())
    asyncio.run(system.check_updates())
    asyncio.run(system.check_updates())  # второй раз за сутки не проверяет
    assert len(sent) == 1 and sent[0][0] == "me" and "Первая правка" in sent[0][1]

    system.db.set("last_check", 0)
    asyncio.run(system.check_updates())  # то же обновление второй раз не присылается
    assert len(sent) == 1


def test_inline_confirmation(tmp_path, monkeypatch):
    env = make_env(tmp_path, builtins=True)
    monkeypatch.setattr(updater, "is_git_checkout", lambda: True)
    monkeypatch.delenv("UROBOROS_DOCKER", raising=False)
    fake = FakeGit()
    monkeypatch.setattr(updater, "run_process", fake)
    restarted = []

    async def fake_restart(client):
        restarted.append(True)

    monkeypatch.setattr("uroboros.utils.restart", fake_restart)
    asyncio.run(env.loader.get_command("update").func(InlineMessage(".update")))
    assert not fake.ran("merge")
    press(env.manager, "✅ Обновить")
    assert fake.ran("merge") and restarted == [True]
    assert env.bot.edits()[-1]["text"] == "🔄 <b>Обновлено</b> · перезапуск..."
    env.db.close()


def test_version_key_and_latest_release():
    assert updater.version_key("1.1.0") > updater.version_key("1.1.0.dev0") > updater.version_key("1.0.9")
    assert updater.version_key("1.1.0-dev") == updater.version_key("1.1.0.dev0")
    releases = {
        "1.0.0": [{"yanked": False}],
        "1.1.0.dev0": [{"yanked": False}],
        "1.0.1": [{"yanked": True}],
        "0.9.0": [],
        "junk": [{}],
    }
    assert updater.latest_release(releases, "stable") == "1.0.0"
    assert updater.latest_release(releases, "beta") == "1.1.0.dev0"


@pytest.fixture
def pip_install(monkeypatch):
    monkeypatch.setattr(updater, "is_git_checkout", lambda: False)
    monkeypatch.setattr(updater, "distribution", lambda: "uroboros-userbot")
    monkeypatch.setattr(updater, "_pypi_releases", lambda dist: {"1.0.0": [{}], "1.2.0": [{}], "1.3.0.dev0": [{}]})


def test_check_pip(pip_install):
    update = asyncio.run(updater.check_pip("stable", "1.0.0"))
    assert update.target == "uroboros-userbot==1.2.0" and update.label == "PyPI 1.2.0"
    assert asyncio.run(updater.check_pip("beta", "1.0.0")).target.endswith("==1.3.0.dev0")
    assert asyncio.run(updater.check_pip("stable", "1.2.0")) is None


def test_install_pip_rolls_back(pip_install, monkeypatch):
    calls = []

    async def fake_run(*args):
        calls.append(args)
        return (1, "boom") if args[1] == "-c" else (0, "")

    monkeypatch.setattr(updater, "run_process", fake_run)
    update = asyncio.run(updater.check_pip("stable", "1.0.0"))
    with pytest.raises(updater.InstallError) as error:
        asyncio.run(updater.install_pip(update, "1.0.0"))
    assert error.value.rolled_back and error.value.stage == "Новая версия не запускается"
    assert calls[0][-1] == "uroboros-userbot==1.2.0" and calls[-1][-1] == "uroboros-userbot==1.0.0"


def test_update_command_from_pypi(builtin_loader, pip_install, monkeypatch):
    monkeypatch.delenv("UROBOROS_DOCKER", raising=False)
    system = builtin_loader.get_module("system")
    system.db.set("channel", "stable")
    message = FakeMessage(".update")
    asyncio.run(system.update(message))
    assert "PyPI 1.2.0" in message.edits[-1] and "релизах на GitHub" in message.edits[-1]

    message = FakeMessage(".dev")
    asyncio.run(system.dev(message))
    assert "<code>master</code>" in message.edits[-1]


OLD_SHA, NEW_SHA = "a" * 40, "b" * 40


@pytest.fixture
def pip_dev(pip_install, monkeypatch):
    """pip-установка, переключаемая между PyPI и архивами dev; ``state["url"]`` — direct_url.json."""
    state = {"url": "", "calls": [], "fail": None}

    async def dev_head():
        return NEW_SHA

    async def source(url):
        assert url.endswith(f"/{NEW_SHA}/uroboros/__init__.py")
        return '__version__ = "1.3.0-dev"\n'

    async def fake_run(*args):
        state["calls"].append(args)
        if state["fail"] and state["fail"] in args:
            return 1, "boom"
        return 0, ""

    monkeypatch.setattr(updater, "_direct_url", lambda: state["url"])
    monkeypatch.setattr(updater, "_dev_head", dev_head)
    monkeypatch.setattr(updater, "download_source", source)
    monkeypatch.setattr(updater, "run_process", fake_run)
    monkeypatch.setattr(updater, "_compare", lambda old, new: ["bbbbbbb Новое", "ccccccc Ещё"])
    return state


def test_pip_branch_from_direct_url(pip_dev):
    assert updater.pip_branch() == "master" and updater.pip_commit() is None
    pip_dev["url"] = updater.archive_url(OLD_SHA)
    assert updater.pip_branch() == "dev" and updater.pip_commit() == OLD_SHA
    pip_dev["url"] = "https://example.com/archive/" + OLD_SHA + ".zip"
    assert updater.pip_commit() is None


def test_pip_switch_to_dev_and_back(pip_dev):
    target = asyncio.run(updater.prepare_switch_pip("dev", "1.2.0"))
    assert (target.previous, target.version, target.spec) == ("master", "1.3.0-dev", updater.archive_url(NEW_SHA))
    asyncio.run(updater.switch_pip(target))
    first, second, check = pip_dev["calls"]
    assert "--force-reinstall" in first and "--no-deps" in first and first[-1] == target.spec
    assert "--force-reinstall" not in second and second[-1] == target.spec and "-c" in check

    pip_dev["url"], pip_dev["calls"] = target.spec, []
    with pytest.raises(updater.UpdateError, match="Уже стоит ветка dev"):
        asyncio.run(updater.prepare_switch_pip("dev", "1.3.0-dev"))
    target = asyncio.run(updater.prepare_switch_pip("master", "1.3.0-dev"))
    assert (target.previous, target.spec) == ("dev", "uroboros-userbot==1.2.0")


def test_pip_switch_rolls_back_to_dev_archive(pip_dev):
    pip_dev["url"] = updater.archive_url(OLD_SHA)
    target = asyncio.run(updater.prepare_switch_pip("master", "1.3.0-dev"))
    pip_dev["fail"] = "-c"
    with pytest.raises(updater.InstallError) as error:
        asyncio.run(updater.switch_pip(target))
    assert error.value.rolled_back
    assert pip_dev["calls"][-1][-1] == updater.archive_url(OLD_SHA)


def test_check_pip_on_dev_follows_commits(pip_dev):
    pip_dev["url"] = updater.archive_url(OLD_SHA)
    update = asyncio.run(updater.check_pip("stable", "1.3.0-dev"))
    assert update.target == updater.archive_url(NEW_SHA) and update.label == "dev bbbbbbb"
    assert update.commits == ["bbbbbbb Новое", "ccccccc Ещё"]
    pip_dev["url"] = updater.archive_url(NEW_SHA)
    assert asyncio.run(updater.check_pip("beta", "1.3.0-dev")) is None


def test_dev_command_on_pip(builtin_loader, pip_dev, monkeypatch):
    monkeypatch.delenv("UROBOROS_DOCKER", raising=False)
    system = builtin_loader.get_module("system")
    restarted = []

    async def fake_restart(message):
        restarted.append(message)

    system.restart = fake_restart
    message = FakeMessage(".dev on -f")
    asyncio.run(system.dev(message))
    assert restarted and any(updater.archive_url(NEW_SHA) in call for call in pip_dev["calls"])
    assert system.db.get("channel") == "beta"
