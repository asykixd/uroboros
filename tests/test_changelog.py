"""scripts/changelog.py: grouping Conventional Commits into release sections."""

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "changelog.py"


@pytest.fixture(scope="module")
def changelog():
    spec = importlib.util.spec_from_file_location("changelog", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["changelog"] = module  # dataclasses look up their module here
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop("changelog", None)


@pytest.mark.parametrize(
    ("subject", "body", "section", "line"),
    [
        ("feat(loader): add pins", "", "Features", "- **loader:** add pins (abc1234)"),
        ("fix: keep the bot running", "", "Fixes", "- keep the bot running (abc1234)"),
        ("build: drop py39", "", "CI and build", "- drop py39 (abc1234)"),
        ("feat(api)!: rename answer", "", "Breaking changes", "- **api:** rename answer (abc1234)"),
        ("refactor: split utils", "BREAKING CHANGE: utils.x is gone", "Breaking changes", "- split utils (abc1234)"),
        ("style: reformat", "", "Other", "- reformat (abc1234)"),
        ("Merge dev into master", "", "Other", "- Merge dev into master (abc1234)"),
    ],
)
def test_classify(changelog, subject, body, section, line):
    assert changelog.classify(changelog.Commit("abc1234", subject, body)) == (section, line)


def test_render_orders_sections_and_skips_empty_releases(changelog):
    commits = [
        changelog.Commit("1111111", "chore: bump version"),
        changelog.Commit("2222222", "fix(web): escape errors"),
        changelog.Commit("3333333", "feat!: new config format"),
        changelog.Commit("4444444", "feat: add .backup"),
    ]
    releases = [
        changelog.Release("Unreleased", None, []),
        changelog.Release("1.2.0", "2026-10-20", commits),
    ]
    text = changelog.render(releases, [("v1.0.0", "2026-10-05")])

    assert "## Unreleased" not in text
    assert "## 1.2.0 (2026-10-20)" in text
    headings = [line for line in text.splitlines() if line.startswith("### ")]
    assert headings == ["### Breaking changes", "### Features", "### Fixes", "### Chores"]
    assert text.index("- new config format (3333333)") < text.index("- add .backup (4444444)")
    assert "## Earlier" in text and "- 1.0.0 (2026-10-05)" in text
    assert text.endswith("\n") and not text.endswith("\n\n")
