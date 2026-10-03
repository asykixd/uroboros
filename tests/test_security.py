import asyncio
from types import SimpleNamespace

import pytest
from conftest import FakeMessage

from uroboros import command
from uroboros.database import Database
from uroboros.decorators import COMMAND_ATTR
from uroboros.dispatcher import Dispatcher
from uroboros.loader import Command, Loader
from uroboros.security import Security

ME, FRIEND, HELPER, STRANGER = 1, 2, 3, 4


@pytest.fixture
def security():
    db = Database(":memory:")
    security = Security(db)
    security.me_id = ME
    yield security
    db.close()


def make_command(access="sudo", name="x"):
    calls = []

    @command(name, access=access)
    async def handler(message):
        calls.append(message)

    return Command(getattr(handler, COMMAND_ATTR), handler, module=None), calls


def test_levels(security):
    security.add("sudo", FRIEND)
    security.add("support", HELPER)
    assert [security.level_of(u) for u in (ME, FRIEND, HELPER, STRANGER, None)] == [
        "owner",
        "sudo",
        "support",
        "everyone",
        "everyone",
    ]
    cmd, _ = make_command("support")
    assert [security.can_run(cmd, u) for u in (ME, FRIEND, HELPER, STRANGER)] == [True, True, True, False]
    owner_cmd, _ = make_command("owner")
    assert [security.can_run(owner_cmd, u) for u in (ME, FRIEND, HELPER)] == [True, False, False]


def test_user_is_in_one_group(security):
    assert security.add("sudo", FRIEND)
    assert not security.add("sudo", FRIEND)
    security.add("owner", FRIEND)
    assert security.members("sudo") == [] and security.level_of(FRIEND) == "owner"
    assert security.remove("owner", FRIEND) and not security.remove("owner", FRIEND)


def test_overrides(security):
    cmd, _ = make_command("owner")
    security.set_required("x", "everyone")
    assert security.can_run(cmd, STRANGER)
    security.set_required("x", None)
    assert security.required(cmd) == "owner"
    with pytest.raises(ValueError):
        security.set_required("x", "admins")


def test_invalid_access():
    with pytest.raises(ValueError):
        command("x", access="admins")


class Incoming(FakeMessage):
    out = False

    def __init__(self, text, sender_id):
        super().__init__(text)
        self.sender_id = sender_id
        self.replies = []

    async def reply(self, text, **kwargs):
        self.replies.append(text)
        return self


def dispatch(tmp_path, cmd, message, setup=None):
    db = Database(":memory:")
    loader = Loader(None, db, tmp_path)
    loader.security.me_id = ME
    loader.commands[cmd.name] = cmd
    if setup:
        setup(loader.security)
    dispatcher = Dispatcher(None, db, loader)
    asyncio.run(dispatcher._on_message(SimpleNamespace(message=message)))
    db.close()


def test_incoming_commands_need_rights(tmp_path):
    cmd, calls = make_command("sudo")
    dispatch(tmp_path, cmd, Incoming(".x", STRANGER))
    assert calls == []

    dispatch(tmp_path, cmd, Incoming(".x", FRIEND), lambda s: s.add("sudo", FRIEND))
    assert len(calls) == 1

    dispatch(tmp_path, cmd, Incoming(".x", HELPER), lambda s: s.add("support", HELPER))
    assert len(calls) == 1

    dispatch(tmp_path, cmd, Incoming(".x", STRANGER), lambda s: s.set_required("x", "everyone"))
    assert len(calls) == 2

    own = FakeMessage(".x")
    dispatch(tmp_path, cmd, own)
    assert calls[-1] is own


def run(loader, text, message=None):
    message = message or FakeMessage(text)
    message.raw_text = text
    asyncio.run(loader.get_command(text.split()[0][1:]).func(message))
    return message.edits[-1]


def test_security_commands(builtin_loader, monkeypatch):
    loader = builtin_loader
    loader.security.me_id = ME

    async def target(message, arg=None):
        return SimpleNamespace(id=int(arg)) if arg else None

    monkeypatch.setattr("uroboros.utils.get_target", target)
    assert "добавлен в <b>sudo</b>" in run(loader, f".sudo add {FRIEND}")
    assert "уже в <b>sudo</b>" in run(loader, f".sudo add {FRIEND}")
    assert loader.security.level_of(FRIEND) == "sudo"
    assert "и так владелец" in run(loader, f".owner add {ME}")
    assert f"<code>{FRIEND}</code>" in run(loader, ".sudo")

    assert "все" in run(loader, ".security ping everyone")
    assert loader.security.required(loader.get_command("ping")) == "everyone"
    assert "(по умолчанию)" in run(loader, ".security ping default")
    assert "❌" in run(loader, ".security ping admins")
    assert "Доступ" in run(loader, ".security")
    assert "доступ: владельцы" in run(loader, ".help eval")
    assert "удалён из <b>sudo</b>" in run(loader, f".sudo del {FRIEND}")


def test_dangerous_builtins_are_owner_only(builtin_loader):
    for name in ("e", "t", "dlm", "ulm", "lm", "restore", "update", "security", "sudo"):
        assert builtin_loader.get_command(name).info.access == "owner", name
