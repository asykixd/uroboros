# Contributing

Thanks for helping! Docs and commits are in English; the bot interface is in Russian for now.

## Branches

- `dev`: development, send pull requests here;
- `master`: stable releases, updated only by merging `dev`.

## Before a pull request

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev,docs]'
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/python -m pytest
```

- Tests don't touch the network or Telegram; keep it that way.
- The public API is recorded in `tests/api_snapshot.json`; see [docs/stability.md](docs/stability.md).
- Changed a built-in command or an example? Regenerate the reference: `python scripts/gen_docs.py`.
- Bot replies are cards via `utils.card(...)`, see [docs/modules.md](docs/modules.md#reply-style).
- Docs pages come in pairs: `page.md` (English) and `page.ru.md` (Russian). Update both.

## Modules

Keep your modules in your own repo, using [uroboros-modules](https://github.com/asykixd/uroboros-modules) as a
template. Useful modules can be proposed there.
