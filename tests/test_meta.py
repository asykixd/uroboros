import asyncio

import pytest

from uroboros import __version__
from uroboros.database import Database
from uroboros.loader import Loader, LoadError, parse_meta, version_tuple

BODY = "from uroboros import Module\nclass Meta(Module):\n    pass\n"


@pytest.fixture
def loader(tmp_path):
    return Loader(None, Database(":memory:"), tmp_path)


def test_parse_meta():
    src = "# meta developer: @someone\n#meta Version: 1.2.3\n# meta: broken\n" + BODY
    assert parse_meta(src) == {"developer": "@someone", "version": "1.2.3"}


@pytest.mark.parametrize(
    ("version", "expected"),
    [("0.2", (0, 2, 0)), ("0.1.1b2", (0, 1, 1)), ("1", (1, 0, 0)), ("10.20.30", (10, 20, 30))],
)
def test_version_tuple(version, expected):
    assert version_tuple(version) == expected


def test_meta_is_stored(loader):
    (inst,) = asyncio.run(loader.install("# meta developer: @me\n" + BODY, "x"))
    assert inst._meta == {"developer": "@me"}


def test_requires_uroboros_ok(loader):
    asyncio.run(loader.install("# requires_uroboros: 0.1\n" + BODY, "x"))
    asyncio.run(loader.install(f"# requires_uroboros: >={__version__}\n" + BODY, "x"))


def test_requires_newer_uroboros_is_rejected_before_exec(loader):
    src = "# requires_uroboros: 99.0\nraise SystemExit('код не должен выполняться')\n" + BODY
    with pytest.raises(LoadError, match=r"99\.0 или новее"):
        asyncio.run(loader.install(src, "x"))


def test_requires_uroboros_garbage(loader):
    with pytest.raises(LoadError, match="Непонятная версия"):
        asyncio.run(loader.install("# requires_uroboros: latest\n" + BODY, "x"))
