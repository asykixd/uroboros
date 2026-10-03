import asyncio
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("hikka_compat", ROOT / "scripts" / "hikka_compat.py")
compat = importlib.util.module_from_spec(spec)
sys.modules["hikka_compat"] = compat
spec.loader.exec_module(compat)

DEMO = (Path(__file__).parent / "hikka" / "demo.py").read_text("utf-8")


def check(source, tmp_path):
    return asyncio.run(compat.check_source(source, tmp_path))


def test_compatible_module(tmp_path):
    status, detail = check(DEMO, tmp_path)
    assert status == compat.OK and detail == "команд: 5"


def test_missing_requirements_are_not_installed(tmp_path):
    source = "# requires: definitely-not-installed-pkg\nimport definitely_not_installed_pkg\nfrom .. import loader\n"
    assert check(source, tmp_path) == (compat.DEPS, "нужны пакеты: definitely-not-installed-pkg")


def test_broken_modules(tmp_path):
    assert check("from ..database import Database\n", tmp_path)[0] == compat.FAIL
    status, detail = check("from .. import loader\nraise SystemExit(1)\n", tmp_path)
    assert status == compat.FAIL and "SystemExit" in detail


def test_render():
    text = compat.render(
        [compat.Result("o/r", "a.py", compat.OK, "команд: 1"), compat.Result("o/r", "b.py", compat.FAIL, "x | y")]
    )
    assert "**1** из 2 (50%)" in text and "x \\| y" in text
