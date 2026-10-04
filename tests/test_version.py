"""Версия: одна и та же в pyproject.toml и uroboros/__init__.py, в master — без -dev, в dev — с -dev."""

import os
import re
import subprocess
from pathlib import Path

import pytest

from uroboros import __version__

ROOT = Path(__file__).resolve().parent.parent
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(-dev)?$")


def current_branch() -> str | None:
    # В GitHub Actions HEAD отсоединён: ветку берём из переменных окружения.
    for name in ("GITHUB_HEAD_REF", "GITHUB_REF_NAME"):
        if os.environ.get(name):
            return os.environ[name]
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip()


def test_version_matches_pyproject():
    match = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.MULTILINE)
    assert match is not None
    assert match[1] == __version__
    assert VERSION_RE.match(__version__), __version__


@pytest.mark.parametrize(("branch", "dev"), [("master", False), ("dev", True)])
def test_version_suffix_matches_branch(branch, dev):
    if current_branch() != branch:
        pytest.skip(f"не на ветке {branch}")
    assert __version__.endswith("-dev") == dev, f"в {branch} версия {'с' if dev else 'без'} -dev, сейчас {__version__}"
