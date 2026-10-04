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


SHA = "0123456789abcdef0123456789abcdef01234567"


def test_split_raw_and_commit_link():
    from uroboros.github import commit_link, split_raw

    assert split_raw(f"{RAW}/o/r/HEAD/dir/mod.py") == ("o/r", "HEAD", "dir/mod.py")
    assert split_raw(f"{RAW}/o/r/HEAD") is None
    assert split_raw("https://example.com/o/r/HEAD/mod.py") is None
    assert commit_link(f"{RAW}/o/r/{SHA}/mod.py") == f"https://github.com/o/r/commit/{SHA}"
    assert commit_link(f"{RAW}/o/r/main/mod.py") is None


def test_pin(monkeypatch):
    import asyncio

    from uroboros import github

    calls = []

    def resolve(repo, ref):
        calls.append((repo, ref))
        return SHA

    monkeypatch.setattr(github, "resolve_commit", resolve)
    assert asyncio.run(github.pin(f"{RAW}/o/r/HEAD/mod.py")) == (f"{RAW}/o/r/{SHA}/mod.py", SHA)
    assert asyncio.run(github.pin(f"{RAW}/o/r/{SHA}/mod.py")) == (f"{RAW}/o/r/{SHA}/mod.py", SHA)
    assert asyncio.run(github.pin("https://example.com/mod.py")) is None
    assert calls == [("o/r", "HEAD")]


def test_pin_falls_back_when_api_fails():
    import asyncio

    from uroboros import github

    # conftest подменяет resolve_commit ошибкой сети
    assert asyncio.run(github.pin(f"{RAW}/o/r/HEAD/mod.py")) is None
