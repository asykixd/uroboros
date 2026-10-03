"""Публичный API заморожен: любое изменение сигнатур видно в этом тесте.

Изменили API сознательно (новое — можно, ломать — только по docs/stability.md) — обновите слепок:
    UPDATE_API_SNAPSHOT=1 .venv/bin/python -m pytest tests/test_public_api.py
"""

import inspect
import json
import os
from pathlib import Path

import uroboros
from uroboros import errors, inline, utils, validators
from uroboros.inline import types as inline_types

SNAPSHOT = Path(__file__).parent / "api_snapshot.json"


def describe(obj):
    if inspect.isclass(obj):
        methods = {
            name: str(inspect.signature(member))
            for name, member in vars(obj).items()
            if not name.startswith("_") and callable(member)
        }
        properties = sorted(name for name, member in vars(obj).items() if isinstance(member, property))
        try:
            init = str(inspect.signature(obj.__init__))
        except (TypeError, ValueError):
            init = ""
        return {"init": init, "methods": methods, "properties": properties}
    if callable(obj):
        return str(inspect.signature(obj))
    return type(obj).__name__


def public(module, names=None):
    names = names or [n for n in vars(module) if not n.startswith("_")]
    result = {}
    for name in sorted(names):
        obj = getattr(module, name)
        if inspect.ismodule(obj):
            continue
        if getattr(obj, "__module__", module.__name__) != module.__name__ and names is None:
            continue
        result[name] = describe(obj)
    return result


def snapshot():
    return {
        "uroboros": public(uroboros, [n for n in uroboros.__all__ if n != "__version__"]),
        "uroboros.utils": {
            name: describe(getattr(utils, name))
            for name in sorted(vars(utils))
            if not name.startswith("_")
            and (inspect.isfunction(getattr(utils, name)) or inspect.isclass(getattr(utils, name)))
            and getattr(getattr(utils, name), "__module__", "") == "uroboros.utils"
        },
        "uroboros.validators": public(validators),
        "uroboros.errors": public(errors),
        "uroboros.inline": public(inline, ["Inline", "InlineCall", "InlineMessage", "InlineQuery"]),
        "uroboros.inline.types": {"KEEP": "KEEP", "ACTION_KEYS": list(inline_types.ACTION_KEYS)},
    }


def test_public_api_is_unchanged():
    current = snapshot()
    if os.environ.get("UPDATE_API_SNAPSHOT"):
        SNAPSHOT.write_text(json.dumps(current, ensure_ascii=False, indent=1, sort_keys=True) + "\n", "utf-8")
    expected = json.loads(SNAPSHOT.read_text("utf-8"))
    removed = {
        f"{section}.{name}"
        for section, items in expected.items()
        for name in items
        if name not in current.get(section, {})
    }
    changed = {
        f"{section}.{name}"
        for section, items in expected.items()
        for name, value in items.items()
        if name in current.get(section, {}) and current[section][name] != value
    }
    assert not removed, f"Из публичного API пропало: {sorted(removed)} — это ломающее изменение (docs/stability.md)"
    assert not changed, (
        f"Изменились сигнатуры: {sorted(changed)}. Если это сознательно — обновите слепок (см. докстринг)"
    )
    added = {
        f"{section}.{name}"
        for section, items in current.items()
        for name in items
        if name not in expected.get(section, {})
    }
    assert not added, f"Новое в публичном API: {sorted(added)}. Добавьте в слепок (см. докстринг) и в документацию"


def test_deprecation_helper(caplog):
    import warnings

    from uroboros.deprecation import deprecated

    @deprecated(since="1.1", removed_in="2.0", alternative="new_func")
    def old_func():
        return 1

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert old_func() == 1
        assert old_func() == 1
    assert len(caught) == 2 and issubclass(caught[0].category, DeprecationWarning)
    assert "используйте new_func" in str(caught[0].message)
    assert sum("old_func" in r.message for r in caplog.records) == 1  # в лог — один раз
