"""Generates CHANGELOG.md from Conventional Commits, grouped by type between release tags.

Usage: python scripts/changelog.py [--stdout]

Release tags are ``vX.Y.Z`` (``-dev`` tags are skipped). Tags sit on master merge commits, so a release section holds
the non-merge commits reachable from its tag and not from the previous one. History before ``CUTOFF`` doesn't follow
Conventional Commits: releases that add nothing after it are listed under one "Earlier" section.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "CHANGELOG.md"
RELEASES_URL = "https://github.com/asykixd/uroboros/releases"
# The first commit written as a Conventional Commit.
CUTOFF = "3fa1e14"

# Section order in each release; types not listed here go to "Other".
GROUPS = {
    "feat": "Features",
    "fix": "Fixes",
    "perf": "Performance",
    "refactor": "Refactoring",
    "docs": "Documentation",
    "test": "Tests",
    "ci": "CI and build",
    "build": "CI and build",
    "chore": "Chores",
}
BREAKING = "Breaking changes"
OTHER = "Other"
SUBJECT_RE = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]+)\))?(?P<bang>!)?: (?P<summary>.+)$")


@dataclass
class Commit:
    sha: str
    subject: str
    body: str = ""


@dataclass
class Release:
    title: str
    date: str | None
    commits: list[Commit]


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def classify(commit: Commit) -> tuple[str, str]:
    """(section, changelog line) for one commit."""
    match = SUBJECT_RE.match(commit.subject)
    if match is None:
        return OTHER, f"- {commit.subject} ({commit.sha})"
    scope = f"**{match['scope']}:** " if match["scope"] else ""
    line = f"- {scope}{match['summary']} ({commit.sha})"
    if match["bang"] or "BREAKING CHANGE" in commit.body:
        return BREAKING, line
    return GROUPS.get(match["type"], OTHER), line


def render_release(release: Release) -> str:
    sections: dict[str, list[str]] = {}
    for commit in release.commits:
        section, line = classify(commit)
        sections.setdefault(section, []).append(line)
    order = [BREAKING, *dict.fromkeys(GROUPS.values()), OTHER]
    heading = f"## {release.title}" + (f" ({release.date})" if release.date else "")
    parts = [heading]
    for section in order:
        if section in sections:
            parts.append(f"### {section}\n\n" + "\n".join(sections[section]))
    return "\n\n".join(parts)


def render(releases: list[Release], earlier: list[tuple[str, str]]) -> str:
    parts = [
        "# Changelog\n\nGenerated from Conventional Commits by `scripts/changelog.py`; don't edit by hand.",
        *(render_release(release) for release in releases if release.commits),
    ]
    if earlier:
        versions = "\n".join(f"- {tag.removeprefix('v')} ({date})" for tag, date in earlier)
        parts.append(
            "## Earlier\n\nThese releases predate Conventional Commits; their notes are on "
            f"[GitHub Releases]({RELEASES_URL}).\n\n{versions}"
        )
    return "\n\n".join(parts) + "\n"


def log(*revisions: str) -> list[Commit]:
    """Non-merge commits after the cutoff, newest first."""
    out = git("log", "--no-merges", "--format=%h%x1f%s%x1f%b%x1e", *revisions, f"^{CUTOFF}^")
    commits = []
    for record in out.split("\x1e"):
        if record.strip():
            sha, subject, body = record.strip("\n").split("\x1f")
            commits.append(Commit(sha, subject, body))
    return commits


def collect() -> tuple[list[Release], list[tuple[str, str]]]:
    tags = []
    for line in git(
        "tag", "--list", "v*", "--sort=creatordate", "--format=%(refname:short) %(creatordate:short)"
    ).split("\n"):
        if line and "-dev" not in line:
            tag, date = line.split()
            tags.append((tag, date))

    releases, earlier = [], []
    previous: list[str] = []
    for tag, date in tags:
        commits = log(tag, *(f"^{p}" for p in previous))
        if commits:
            releases.append(Release(tag.removeprefix("v"), date, commits))
        else:
            earlier.append((tag, date))
        previous.append(tag)
    releases.append(Release("Unreleased", None, log("HEAD", *(f"^{p}" for p in previous))))
    return releases[::-1], earlier[::-1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--stdout", action="store_true", help="print instead of writing CHANGELOG.md")
    args = parser.parse_args()
    text = render(*collect())
    if args.stdout:
        sys.stdout.write(text)
    else:
        OUTPUT.write_text(text, "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
