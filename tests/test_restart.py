import sys

import pytest

from uroboros import main, utils


def test_windows_restart_exits_with_restart_code(monkeypatch):
    monkeypatch.setattr(utils, "IS_WINDOWS", True)
    with pytest.raises(SystemExit) as exc:
        utils.exec_restart()
    assert exc.value.code == utils.RESTART_EXIT_CODE


def test_posix_restart_execs_same_interpreter(monkeypatch):
    calls = []
    monkeypatch.setattr(utils, "IS_WINDOWS", False)
    monkeypatch.setattr(utils.os, "execv", lambda path, args: calls.append((path, args)))
    monkeypatch.setattr(sys, "argv", ["uroboros", "--flag"])
    utils.exec_restart()
    assert calls == [(sys.executable, [sys.executable, "-m", "uroboros", "--flag"])]


def test_supervisor_restarts_until_normal_exit(monkeypatch):
    codes = iter([utils.RESTART_EXIT_CODE, utils.RESTART_EXIT_CODE, 3])
    started = []

    class FakePopen:
        def __init__(self, args, env):
            started.append(env[utils.SUPERVISED_ENV])

        def wait(self):
            return next(codes)

    monkeypatch.setattr(main.subprocess, "Popen", FakePopen)
    with pytest.raises(SystemExit) as exc:
        main.supervise()
    assert exc.value.code == 3
    assert started == ["1", "1", "1"]
