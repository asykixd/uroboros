# API stability

Since 1.0 Uroboros follows [semver](https://semver.org/): `MAJOR.MINOR.PATCH`.

- **Patch** (`1.0.1`): fixes only.
- **Minor** (`1.1.0`): new features; existing modules keep working.
- **Major** (`2.0.0`): may remove deprecated APIs, with a changelog and migration notes.

`-dev` versions (`1.1.0-dev`) are `dev` branch builds: new things there may change before reaching `master`. The
guarantees above apply to versions without the suffix.

## Public API

What modules can rely on:

- everything exported by `uroboros` (`Module`, `Library`, `ModuleConfig`, `ConfigValue`, `command`, `watcher`,
  `loop`, `StopLoop`, `inline_handler`, `callback_handler`, `LoadError`, `InlineError`, `utils`, `validators`);
- `uroboros.utils` functions, `uroboros.validators`, `uroboros.errors` exceptions;
- module attributes and methods: `client`, `db`, `loader`, `inline`, `config`, `strings`, `get`, `set`,
  `import_lib`, hooks `on_load`, `on_unload`, `on_dlmod`;
- `self.inline`: `form`, `list`, `gallery`, `markup`, `available`, `bot`; `InlineCall`, `InlineMessage`,
  `InlineQuery`;
- decorator parameters and button format;
- file header: `# meta`, `# requires`, `# requires_uroboros`.

Not included: loader, dispatcher and inline manager internals (`self.loader.*` beyond module and command lists),
`uroboros.hikka` (the adapter follows Hikka, not semver), anything starting with `_`.

Public signatures are recorded in `tests/api_snapshot.json`: `tests/test_public_api.py` fails if anything disappears
or changes without updating the snapshot.

## Deprecation

Nothing is removed at once. A deprecated name:

1. is marked with `uroboros.deprecation.deprecated(since=..., removed_in=..., alternative=...)`;
2. keeps working for at least one minor version, emitting `DeprecationWarning` and one log warning;
3. is removed no earlier than the next major version and listed in its changelog.

```python
from uroboros.deprecation import deprecated

@deprecated(since="1.2", removed_in="2.0", alternative="utils.get_target")
def get_victim(message): ...
```
