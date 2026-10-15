import asyncio

import pytest
from conftest import FakeMessage
from telethon.tl.functions.account import DeleteAccountRequest

from uroboros import guard
from uroboros.ratelimit import module_context

MODULE = """
from uroboros import Module

class Demo(Module):
    pass
"""


def security(loader, text):
    message = FakeMessage(text)
    asyncio.run(loader.get_command("security").func(message))
    return message.edits[-1]


def test_blocks_are_logged_and_bounded(builtin_loader, monkeypatch):
    loader = builtin_loader
    asyncio.run(loader.install(MODULE, "https://example.com/demo.py"))
    module = loader.get_module("demo")
    assert security(loader, ".security log") == "🛡 <b>Блокировок не было</b>"

    with module_context(module):
        with pytest.raises(guard.ModuleBlocked):
            loader.guard.check_request(DeleteAccountRequest(reason="x"))
        # The DB guard blocks the module, but the log write itself goes through.
        with pytest.raises(guard.ModuleBlocked):
            module.db.raw.set("uroboros.security", "owner", [42])
    blocks = loader.guard.blocks()
    assert [(b["module"], b["action"]) for b in blocks] == [
        ("Demo", "удалить аккаунт"),
        ("Demo", "менять системные настройки Uroboros (uroboros.security)"),
    ]
    assert loader.db.get("uroboros.security", "owner") is None

    text = security(loader, ".security log")
    assert text.startswith("🛡 <b>Блокировки защиты</b> · 2") and "<b>Demo</b> — удалить аккаунт" in text
    assert text.index("менять системные") < text.index("удалить аккаунт")  # newest first

    monkeypatch.setattr(guard, "BLOCKS_LIMIT", 3)
    for n in range(5):
        loader.guard.block("Demo", f"действие {n}")
    assert [b["action"] for b in loader.guard.blocks()] == ["действие 2", "действие 3", "действие 4"]

    assert "очищен" in security(loader, ".security log clear")
    assert loader.guard.blocks() == []
