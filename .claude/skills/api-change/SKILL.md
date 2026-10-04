---
name: api-change
description: Checklist for changing the Uroboros public API (anything exported by uroboros/__init__.py, utils, decorators, Module, inline, config). Use for any edit that changes public API signatures or behavior.
---

# Public API change

Public API is what `uroboros/__init__.py` exports (see "Module API" in CLAUDE.md). Policy: `docs/stability.md`.

1. **Compatibility.** Never remove or change a signature silently: keep the old behavior via `uroboros.deprecation.deprecated` with a warning. Only add new things.
2. **API snapshot.** After an intentional change:
   ```bash
   UPDATE_API_SNAPSHOT=1 .venv/bin/python -m pytest tests/test_public_api.py
   ```
   Check the `tests/api_snapshot.json` diff contains only what you meant.
3. **Docs.** Update `docs/modules.md` and `docs/modules.ru.md` (ruff doesn't format their examples, review by eye).
4. **Examples.** `examples/*.py` load in `tests/test_examples.py`. For new API add `# requires_uroboros: X` and make sure `__version__` in `dev` is at least X.
5. **Hikka adapter.** The API mirrors Hikka on purpose. Check the shims in `uroboros/hikka/` (`utils`, `loader`, inline) if `utils.answer`, `strings`, `config` or inline forms changed.
6. **Built-in modules** (`uroboros/modules/`) use the public API only: make sure they don't reach into internals.
7. **Tests:**
   ```bash
   .venv/bin/python -m pytest -q && .venv/bin/ruff check . && .venv/bin/ruff format --check .
   ```
