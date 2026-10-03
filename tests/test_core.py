import asyncio

import pytest

from uroboros.database import LOADER_OWNER, Database, ModuleDB
from uroboros.dispatcher import parse_command
from uroboros.loader import Loader, LoadError, parse_requires
from uroboros.types import ConfigValue, ModuleConfig
from uroboros.validators import Boolean, Integer, ValidationError

DEMO = '''
from uroboros import Module, ModuleConfig, ConfigValue, command, watcher, validators

class Demo(Module):
    """Тестовый модуль"""

    def __init__(self):
        self.config = ModuleConfig(ConfigValue("count", 1, "сколько", validators.Integer(minimum=0)))
        self.loaded = False

    async def on_load(self):
        self.loaded = True

    @command("hi", aliases=["hello"])
    async def hi(self, message):
        """— поздороваться"""

    @watcher(only_incoming=True)
    async def watch(self, message):
        pass
'''


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def db():
    database = Database(":memory:")
    yield database
    database.close()


@pytest.fixture
def loader(db, tmp_path):
    return Loader(None, db, tmp_path / "modules")


# --- парсер команд ---


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (".ping", ("ping", "")),
        (".E print(1)\nprint(2)", ("e", "print(1)\nprint(2)")),
        ("!!dlm https://x", None),
        (". ping", None),
        (".", None),
        ("ping", None),
    ],
)
def test_parse_command(text, expected):
    assert parse_command(text, ".") == expected


def test_parse_command_multichar_prefix():
    assert parse_command("!!dlm url", "!!") == ("dlm", "url")


def test_parse_requires():
    assert parse_requires("# requires: requests  aiofiles\nimport x\n#requires: pillow") == [
        "requests",
        "aiofiles",
        "pillow",
    ]


# --- БД и конфиг ---


def test_database_roundtrip(tmp_path):
    path = tmp_path / "db.sqlite"
    database = Database(path)
    database.set("mod", "key", {"a": (1, 2)})
    value = database.get("mod", "key")
    value["a"].append(3)  # изменение копии не трогает кеш
    assert database.get("mod", "key") == {"a": [1, 2]}
    database.close()

    database = Database(path)
    assert database.get("mod", "key") == {"a": [1, 2]}
    database.delete("mod", "key")
    assert database.get("mod", "key", "def") == "def"
    database.close()


def test_module_config(db):
    config = ModuleConfig(
        ConfigValue("n", 5, validator=Integer(minimum=1)),
        ConfigValue("on", False, validator=Boolean()),
    )
    config._bind(ModuleDB(db, "M"))
    assert config["n"] == 5
    config["n"] = "7"
    config["on"] = "да"
    assert (config["n"], config["on"]) == (7, True)
    with pytest.raises(ValidationError):
        config["n"] = "0"
    config.reset("n")
    assert config["n"] == 5


# --- загрузчик ---


def test_load_builtins(loader):
    run(loader.load_all())
    for name in ("help", "loader", "settings", "config", "eval", "system"):
        assert loader.get_module(name) is not None, name
        assert loader.get_module(name).is_builtin
    assert loader.get_command("ping") is not None
    assert loader.get_command("modules").name == "help"


def test_install_and_uninstall(loader, db, tmp_path):
    (inst,) = run(loader.install(DEMO, "https://example.com/demo.py"))
    assert inst.loaded
    assert loader.get_command("hello").module is inst
    assert len(loader.watchers) == 1
    assert (tmp_path / "modules" / "demo.py").exists()
    assert db.get(LOADER_OWNER, "installed") == {"demo": "https://example.com/demo.py"}

    inst.config["count"] = "3"
    assert db.get("Demo", "__config__") == {"count": 3}

    run(loader.uninstall("DEMO"))
    assert loader.get_module("demo") is None
    assert loader.get_command("hi") is None
    assert loader.watchers == []
    assert not (tmp_path / "modules" / "demo.py").exists()
    assert db.get(LOADER_OWNER, "installed") == {}


def test_reinstall_replaces(loader):
    run(loader.install(DEMO, "a"))
    (inst,) = run(loader.install(DEMO.replace('"hi"', '"hey"'), "b"))
    assert loader.get_command("hi") is None
    assert loader.get_command("hey").module is inst
    assert len(loader.watchers) == 1


def test_persisted_modules_load_after_restart(loader, db, tmp_path):
    run(loader.install(DEMO, "a"))
    fresh = Loader(None, db, tmp_path / "modules")
    run(fresh.load_all())
    assert fresh.get_module("demo") is not None
    assert fresh.get_module("demo").config["count"] == 1


def test_cannot_replace_builtin(loader):
    run(loader.load_all())
    src = "from uroboros import Module\nclass Help(Module):\n    pass\n"
    with pytest.raises(LoadError, match="встроенный"):
        run(loader.install(src, "x"))


def test_command_conflict(loader):
    run(loader.install(DEMO, "a"))
    src = DEMO.replace("class Demo", "class Other")
    with pytest.raises(LoadError, match="уже занята"):
        run(loader.install(src, "b"))
    assert loader.get_module("other") is None


def test_bad_sources(loader):
    with pytest.raises(LoadError, match="Синтаксическая"):
        run(loader.install("def (", "x"))
    with pytest.raises(LoadError, match="нет ни одного"):
        run(loader.install("x = 1", "x"))
    with pytest.raises(LoadError, match="зависимости"):
        run(loader.install("import definitely_missing_pkg_xyz", "x"))


def test_failing_on_load_is_unloaded(loader):
    src = (
        "from uroboros import Module, command\n"
        "class Bad(Module):\n"
        "    async def on_load(self):\n"
        "        raise RuntimeError('boom')\n"
        "    @command('bad')\n"
        "    async def bad(self, m): pass\n"
    )
    with pytest.raises(LoadError, match="boom"):
        run(loader.install(src, "x"))
    assert loader.get_module("bad") is None
    assert loader.get_command("bad") is None


def test_unload_all_calls_on_unload_in_reverse_order(loader):
    src = (
        "from uroboros import Module\n"
        "class {name}(Module):\n"
        "    async def on_unload(self):\n"
        "        self.loader.unloaded.append(self.name)\n"
    )
    loader.unloaded = []
    run(loader.load_all())
    run(loader.install(src.format(name="First"), "a"))
    run(loader.install(src.format(name="Second"), "b"))
    run(loader.unload_all())
    assert loader.unloaded == ["Second", "First"]
    assert loader.modules == {} and loader.commands == {}
