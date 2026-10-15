# Contributing

Thanks for helping! Docs and commits are in English; the bot interface is in Russian for now.

## Branches

- `dev`: development, send pull requests here;
- `master`: stable releases, updated only by merging `dev`.

## Before a pull request

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev,docs]'
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy
.venv/bin/python -m pytest --cov   # CI fails below the coverage threshold in pyproject.toml
```

- Tests don't touch the network or Telegram; keep it that way.
- The public API is recorded in `tests/api_snapshot.json`; see [docs/stability.md](docs/stability.md).
- Changed a built-in command or an example? Regenerate the reference: `python scripts/gen_docs.py`.
- Bot replies are cards via `utils.card(...)`, see [docs/modules.md](docs/modules.md#reply-style).
- Commits follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat(scope): summary`):
  `CHANGELOG.md` is generated from them with `python scripts/changelog.py` before a release.
- Docs pages come in pairs: `page.md` (English) and `page.ru.md` (Russian). Update both.

## Modules

Keep your modules in your own repo: copy [`templates/modules-repo/`](templates/modules-repo) (example module,
README and a CI check that scans and loads every module). Useful modules can be proposed to
[uroboros-modules](https://github.com/asykixd/uroboros-modules).
