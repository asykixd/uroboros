"""The module repo template (templates/modules-repo) must pass its own check, and the check must catch bad modules."""

import asyncio
import importlib.util
from pathlib import Path

TEMPLATE = Path(__file__).parent.parent / "templates" / "modules-repo"


def load_checker():
    spec = importlib.util.spec_from_file_location("check_modules", TEMPLATE / "tools" / "check_modules.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_template_modules_pass():
    assert asyncio.run(load_checker().main(TEMPLATE)) == 0


def test_check_fails_on_bad_modules(tmp_path, capsys):
    (tmp_path / "broken.py").write_text("from uroboros import Module\n\nclass Broken(Module:\n    pass\n", "utf-8")
    (tmp_path / "stealer.py").write_text(
        "from uroboros import Module\n\n\nclass Stealer(Module):\n"
        "    async def on_load(self):\n        self.client.session.save()\n",
        "utf-8",
    )
    (tmp_path / "_private.py").write_text("raise SystemExit\n", "utf-8")

    assert asyncio.run(load_checker().main(tmp_path)) == 1
    out = capsys.readouterr().out
    assert "broken.py\n  load failed" in out
    assert "stealer.py\n" in out and "  dangerous:" in out
    assert "_private" not in out and "0/2 modules passed" in out


def test_check_fails_on_empty_repo(tmp_path):
    assert asyncio.run(load_checker().main(tmp_path)) == 1
