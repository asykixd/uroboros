import asyncio
import json
import sys

import pytest
from conftest import FakeMessage

from uroboros import healthcheck, main, updater, utils

SHA = "a" * 40


@pytest.fixture
def ran(monkeypatch):
    calls = []

    def fake_run(step):
        calls.append(step)
        return 0, ""

    monkeypatch.setattr(healthcheck, "_run", fake_run)
    return calls


def test_confirm_keeps_new_version(tmp_path):
    healthcheck.arm(tmp_path, updater.Rollback("git", SHA), "1.0.0", "origin/dev")
    pending = healthcheck.begin(tmp_path)
    assert pending.attempts == 1 and pending.previous == "1.0.0" and pending.rollback.ref == SHA
    healthcheck.confirm(tmp_path, healthy=True)
    assert not healthcheck.is_pending(tmp_path) and healthcheck.begin(tmp_path) is None


def test_confirm_without_system_module_is_unhealthy(tmp_path):
    healthcheck.confirm(tmp_path, healthy=False)  # no update pending: nothing to check
    healthcheck.arm(tmp_path, updater.Rollback("git", "master"), "1.0.0", "dev 1.1.0-dev")
    with pytest.raises(healthcheck.UnhealthyError):
        healthcheck.confirm(tmp_path, healthy=False)
    assert healthcheck.is_pending(tmp_path)


def test_marker_never_holds_commands(tmp_path):
    with pytest.raises(ValueError):
        healthcheck.arm(tmp_path, updater.Rollback("git", "; rm -rf ~"), "1.0.0", "x")
    (tmp_path / healthcheck.MARKER).write_text(
        json.dumps({"kind": "pip", "ref": "--index-url=http://evil x", "previous": "1", "target": "2", "attempts": 0})
    )
    assert healthcheck.begin(tmp_path) is None and not healthcheck.is_pending(tmp_path)
    (tmp_path / healthcheck.MARKER).write_text("not json")
    assert healthcheck.begin(tmp_path) is None


def test_git_rollback_steps(tmp_path, ran):
    pending = healthcheck.Pending(updater.Rollback("git", SHA), "1.0.0", "origin/master")
    assert healthcheck.rollback(tmp_path, pending, "boom")
    assert ran[0][-3:] == ("reset", "--keep", SHA) and ran[1][:3] == (sys.executable, "-m", "pip")

    ran.clear()
    pending = healthcheck.Pending(updater.Rollback("git", "master"), "1.0.0", "dev")
    healthcheck.rollback(tmp_path, pending, "boom")
    assert ran[0][-2:] == ("switch", "master")


def test_pip_rollback_steps_and_notice(tmp_path, ran):
    pending = healthcheck.Pending(updater.Rollback("pip", "uroboros-userbot==1.0.0"), "1.0.0", "PyPI 1.1.0")
    assert healthcheck.rollback(tmp_path, pending, "RuntimeError: boom")
    assert ran == [updater._pip_steps("uroboros-userbot==1.0.0")[0]]
    notice = healthcheck.take_notice(tmp_path)
    assert notice["ok"] and notice["previous"] == "1.0.0" and "boom" in notice["reason"]
    assert healthcheck.take_notice(tmp_path) is None


def test_failed_rollback_is_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(healthcheck, "_run", lambda step: (1, "error: local changes"))
    healthcheck.arm(tmp_path, updater.Rollback("git", SHA), "1.0.0", "origin/master")
    pending = healthcheck.begin(tmp_path)
    assert not healthcheck.rollback(tmp_path, pending, "boom")
    notice = healthcheck.take_notice(tmp_path)
    assert not notice["ok"] and "local changes" in notice["output"]
    assert not healthcheck.is_pending(tmp_path)


@pytest.fixture
def start(tmp_path, monkeypatch, ran):
    """``main.main`` with a fake ``run``: returns what happened after it."""
    monkeypatch.setattr(main, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(main.logs, "setup", lambda path: None)
    monkeypatch.setattr(sys, "argv", ["uroboros"])
    monkeypatch.delenv(utils.SUPERVISED_ENV, raising=False)
    monkeypatch.setattr(utils, "IS_WINDOWS", False)
    state = {"runs": 0, "restarts": 0}
    monkeypatch.setattr(utils, "exec_restart", lambda: state.__setitem__("restarts", state["restarts"] + 1))

    def go(behaviour):
        async def fake_run(args):
            state["runs"] += 1
            await behaviour()

        monkeypatch.setattr(main, "run", fake_run)
        main.main()
        return state

    return go


def test_failed_start_after_update_rolls_back(tmp_path, start, ran):
    healthcheck.arm(tmp_path, updater.Rollback("git", SHA), "1.0.0", "origin/master")

    async def crash():
        raise RuntimeError("module system failed")

    state = start(crash)
    assert state == {"runs": 1, "restarts": 1}
    assert ran[0][-1] == SHA
    assert "module system failed" in healthcheck.take_notice(tmp_path)["reason"]


def test_repeated_silent_failures_roll_back_before_running(tmp_path, start, ran):
    healthcheck.arm(tmp_path, updater.Rollback("git", SHA), "1.0.0", "origin/master")
    for _ in range(healthcheck.MAX_ATTEMPTS):
        healthcheck.begin(tmp_path)  # starts killed before they could confirm or roll back

    async def never():
        raise AssertionError("must not run")

    state = start(never)
    assert state == {"runs": 0, "restarts": 1} and ran


def test_failure_without_pending_update_propagates(start, ran):
    async def crash():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        start(crash)
    assert not ran


def test_failure_after_confirm_does_not_roll_back(tmp_path, start, ran):
    healthcheck.arm(tmp_path, updater.Rollback("git", SHA), "1.0.0", "origin/master")

    async def crash_later():
        healthcheck.confirm(tmp_path, healthy=True)
        raise RuntimeError("network")

    with pytest.raises(RuntimeError):
        start(crash_later)
    assert not ran


def test_failed_rollback_stops_instead_of_restarting(tmp_path, start, monkeypatch):
    monkeypatch.setattr(healthcheck, "_run", lambda step: (1, "nope"))
    healthcheck.arm(tmp_path, updater.Rollback("git", SHA), "1.0.0", "origin/master")

    async def crash():
        raise RuntimeError("boom")

    with pytest.raises(SystemExit, match="откатить её не удалось"):
        start(crash)


def test_ctrl_c_during_trial_does_not_roll_back(tmp_path, start, ran):
    healthcheck.arm(tmp_path, updater.Rollback("git", SHA), "1.0.0", "origin/master")

    async def interrupt():
        raise KeyboardInterrupt

    state = start(interrupt)
    assert state["restarts"] == 0 and not ran and healthcheck.is_pending(tmp_path)


def test_update_arms_health_check(builtin_loader, monkeypatch):
    monkeypatch.setattr(updater, "is_git_checkout", lambda: True)
    monkeypatch.delenv("UROBOROS_DOCKER", raising=False)
    system = builtin_loader.get_module("system")
    restarted = []

    async def fake_restart(message):
        restarted.append(message)

    system.restart = fake_restart

    async def install(update):
        return updater.Rollback("git", SHA)

    monkeypatch.setattr(updater, "install", install)
    update = updater.Update(target="origin/master", label="origin/master", sha="b" * 40)
    asyncio.run(system._install(update, lambda text: utils.answer(FakeMessage(), text), FakeMessage()))
    data_dir = builtin_loader.modules_dir.parent
    pending = healthcheck.begin(data_dir)
    assert restarted and pending.rollback.ref == SHA and pending.target == "origin/master"


def test_rollback_is_reported_after_restart(builtin_loader, ran):
    system = builtin_loader.get_module("system")
    data_dir = builtin_loader.modules_dir.parent
    pending = healthcheck.Pending(updater.Rollback("pip", "uroboros-userbot==1.0.0"), "1.0.0", "PyPI 1.1.0")
    healthcheck.rollback(data_dir, pending, "RuntimeError: boom")
    sent = []

    class Client:
        async def send_message(self, chat, text, **kwargs):
            sent.append((chat, text))

    system.client = Client()
    asyncio.run(system.on_load())
    ((chat, text),) = sent
    assert chat == "me" and "Обновление откачено" in text and "1.0.0" in text and "boom" in text
    asyncio.run(system.on_load())
    assert len(sent) == 1
