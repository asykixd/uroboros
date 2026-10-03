import pytest

from uroboros.github import RAW, module_url, parse_repo, to_raw_url


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("owner/repo", "owner/repo"),
        ("https://github.com/owner/repo", "owner/repo"),
        ("https://github.com/owner/repo.git", "owner/repo"),
        ("github.com/owner/my-repo/", "owner/my-repo"),
        ("owner/repo/mod", None),
        ("https://example.com/owner/repo", None),
        ("mod", None),
    ],
)
def test_parse_repo(spec, expected):
    assert parse_repo(spec) == expected


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("https://github.com/o/r/blob/main/dir/mod.py", f"{RAW}/o/r/main/dir/mod.py"),
        ("https://github.com/o/r/raw/dev/mod.py", f"{RAW}/o/r/dev/mod.py"),
        (f"{RAW}/o/r/main/mod.py", f"{RAW}/o/r/main/mod.py"),
        ("o/r/mod", f"{RAW}/o/r/HEAD/mod.py"),
        ("o/r/dir/mod.py", f"{RAW}/o/r/HEAD/dir/mod.py"),
        ("https://example.com/mod.py", None),
        ("o/r", None),
        ("mod", None),
    ],
)
def test_to_raw_url(spec, expected):
    assert to_raw_url(spec) == expected


def test_module_url():
    assert module_url("o/r", "mod") == f"{RAW}/o/r/HEAD/mod.py"
    assert module_url("o/r", "mod.py") == f"{RAW}/o/r/HEAD/mod.py"
