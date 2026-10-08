# CLAUDE.md

Guidance for Claude Code (claude.ai/code) in this repository.

## Project

Uroboros is a modular Telegram userbot (Python ≥3.10 + Telethon 1.x), a from-scratch Hikka alternative. AGPL-3.0, so
Hikka code (also AGPL) may be ported. Branches: `master` stable, `dev` development (see "Branches and versions").

**Language.** English is the primary language of the repo: README, docs, CONTRIBUTING, templates, commit
messages, code comments in new code. Write tersely. Docs come in pairs: `docs/<page>.md` (English) and
`docs/<page>.ru.md` (Russian, mkdocs-static-i18n); `README.md` (English) and `README.ru.md`. Update both. The bot
interface (`uroboros/` messages, `strings`, command docstrings) stays **Russian** until the user asks to translate
it. The user writes in Russian; reply in Russian.

## Commands

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev,docs]'   # dev install
.venv/bin/python -m uroboros                                      # run (no session: web login panel; --cli: console)
.venv/bin/python -m pytest                                        # all tests
.venv/bin/python -m pytest tests/test_core.py::test_install_and_uninstall   # one test
.venv/bin/ruff check . && .venv/bin/ruff format --check .        # lint and format (same as CI)
.venv/bin/mkdocs build --strict                                   # docs site
```

Tests are offline and don't need Telegram: `Loader` is built with `client=None` and `Database(":memory:")`,
coroutines run via `asyncio.run` (no pytest-asyncio).

`api_id`/`api_hash` can come from `UROBOROS_API_ID`/`UROBOROS_API_HASH` (override `config.json`). Runtime data is in
`./data` (`UROBOROS_DATA`): `config.json`, `uroboros.session`, `uroboros.db`, `modules/`, `uroboros.log`,
`uroboros.lock`. That's account access: never commit it, don't read it without need.

## Architecture

Startup in `main.py`: `parse_args` → `connect` (no session: `web.first_login`, aiohttp panel with a token link, shut
down after login; `--cli` for console) → `Database` → `TelegramClient.start` → `InlineManager.start` →
`Loader.load_all` → `Dispatcher.install` → `run_until_disconnected`. Restart: `utils.restart()` sets a flag and
disconnects; `main()` unloads modules after the loop and calls `os.execv`. On Windows `main()` runs a supervisor
(`supervise`) that restarts the child on exit code `RESTART_EXIT_CODE` (75).

**Loader (`loader.py`).** Modules are `exec`'d into a `ModuleType`, not imported:
- Built-ins from `uroboros/modules/*.py` are read as text, named `uroboros.modules.<stem>`.
- Third-party modules are `uroboros.ext.<stem>_<n>`; source saved to `data/modules/<stem>.py`, origin to the DB
  (`uroboros.loader`/`installed`: stem → url).
- The unit of unloading is the file (stem): all `Module` subclasses in a file unload together.
- Order in `_load` matters: conflict checks (can't replace a built-in, can't take another module's command), unload
  replaced stems, register, `on_load`. If `on_load` fails the whole stem rolls back.
- `# requires:` → `pip install` only on `ImportError`, one attempt.
- The header is parsed before `exec`: `# meta key: value` → `inst._meta`; `# requires_uroboros: X` checks the core
  version.
- `LoadError` (`errors.py`, re-exported from `loader`) is shown to the user without a traceback. Downloads:
  `download.py`.

**Dispatcher (`dispatcher.py`).** One `NewMessage` handler. Commands fire on outgoing messages, and on incoming ones
only if the sender's level suffices (`security.py`: `owner` ⊃ `sudo` ⊃ `support` ⊃ `everyone`; groups and overrides
in DB `uroboros.security`, default level from `@command(access=...)`, `"sudo"`). Resolution: prefix → user aliases
(DB `uroboros.main`/`aliases`) → `Loader.get_command` (also handles `@command(aliases=...)`). Watchers get every
message concurrently; their exceptions are only logged.

**Module API** (public = what `uroboros/__init__.py` exports):
- `Module` with `on_load`/`on_unload`.
- `@command`, `@watcher`.
- `ModuleConfig`/`ConfigValue` and `validators` (validators accept strings, since `.cfg` passes text).
- `@loop`, `Library`.
- `@inline_handler`, `@callback_handler`, `self.inline.form` / `list` / `gallery` (`InlineCall`, `InlineError`).
- `utils`: `answer`, `answer_file`, `get_args_raw`, `get_args`, `get_reply`, `get_user`, `get_target`,
  `get_chat_id`, `run_sync`, `quote`, `escape_html`, `Html`, `get_prefix`.

The loader sets `client`, `loader`, `inline`, `db` (`ModuleDB`, owner = module name) on modules, wraps `strings` in
`Strings` (`self.strings("key", **kw)` escapes substitutions) and binds `config` to the DB (key `__config__`). On
stem unload it stops `@loop` tasks (`loops.py`), removes Telethon handlers whose functions are defined in the module
file, and unloads libraries (`Library`, `self.import_lib`) with no remaining users. Library sources are cached in
`data/modules/libs/`, URLs in DB `uroboros.loader`/`libs`. `on_dlmod` is called in `Loader.install` only if the stem
wasn't installed before.

Docs: mkdocs site (`mkdocs.yml`, pages in `docs/`, `.venv/bin/mkdocs build --strict`, published from `master` by
`.github/workflows/docs.yml`). `docs/commands{,.ru}.md` and `docs/examples{,.ru}.md` are generated by
`scripts/gen_docs.py`; `tests/test_docs.py` checks they're current: changed a command or example, regenerate. Module
authors: `docs/modules.md`; security model: `docs/security.md`. The public API is recorded in
`tests/api_snapshot.json` (policy: `docs/stability.md`): for intentional changes run
`UPDATE_API_SNAPSHOT=1 pytest tests/test_public_api.py`; breaking changes only via
`uroboros.deprecation.deprecated`. `examples/` (English) load in `tests/test_examples.py`: update them when the API
changes. An example with `# requires_uroboros: X` won't load if `__version__` is below X, so `dev` and `master`
versions must be at least what examples require (`-dev` ignored in comparison). The API mirrors Hikka on purpose
(`utils.answer`, `strings`, `config`) to keep the compat adapter thin.

**Flood protection (`ratelimit.py`).** `UroborosClient` (`client.py`) counts requests of the third-party module set
in `current_module` (`module_context` around commands, watchers, `@loop`, hooks, callbacks). Over the limit:
`ModuleFrozen` until the freeze ends, notice to Saved Messages. Settings: DB `uroboros.security`/`flood`.

**Inline bot (`inline/`).** aiogram 3 in the same process, `InlineManager` (`loader.inline`). A bot startup failure
doesn't crash the userbot: the reason is in `manager.error`, shown by `.inlinebot`. Token: `UROBOROS_BOT_TOKEN` → DB
(`uroboros.inline`/`token`) → created via @BotFather (`botfather.py`, which also enables inline mode and inline
feedback). Forms: the userbot makes an inline query to its bot with the form id and sends the result (`click`). The
bot learns `inline_message_id` from `chosen_inline_result` or the first press. Input buttons prefill `@bot <id> `,
text arrives in `chosen_inline_result`, and the userbot deletes the `INPUT_MARKER` service message. Forms (`Unit`)
live in memory and are removed on stem unload. The bot answers only the owner and `always_allow`. Modules get the
`self.inline` proxy (`inline.Inline`). Tests stub the bot and client with `tests/fake_inline.py`.

**DB (`database.py`).** Synchronous key-value on `sqlite3` with an in-memory cache (like Hikka's sync
`db.get`/`db.set`). `get` returns a deepcopy; values go through JSON (tuple → list). System owners: `uroboros.main`
(prefix, aliases), `uroboros.loader` (installed, hashes = sha256 of files, pins = commit-pinned GitHub URLs),
`uroboros.inline` (token, configured, disabled), `uroboros.security` (owner, sudo, support, commands).

**GitHub (`github.py`).** Converts blob URLs and short `owner/repo/path` into
`raw.githubusercontent.com/.../HEAD/...`, lists repo modules via the contents API. `.dlm` resolution order:
`owner/repo` → list modules; URL or path → download; bare name → search connected repos (Loader module DB, key
`repos`; default `asykixd/uroboros-modules`, `DEFAULT_REPOS`).

## Bot message style

All replies are HTML via `utils.answer`: it edits your own outgoing message and sends text over 4096 chars as a file.
Style is "cards" (`utils.card(title, body, hint=...)`):
- the title starts with one status emoji and bold text: ✅ success, ❌ error, ⏳ in progress, 🚨 dangerous,
  ⚠️ warning, 📦 modules, ⚙️ settings, 🔐 access, 🗑 removal, 🔗 repos, 🏷 aliases, 🆕 updates, 🌿 branches,
  💾 backup, 🤖 inline bot;
- the body is a quote, each line with one meaningful icon for its field (⏱ time, 📦 modules, 👤 user, 🔗 source,
  📌 commit, 🔐 rights, 📏 size, 🐍 version); list items without their own icon use `▸`;
- the next-step hint is the last line: `💡 <i>...</i>` (`hint=`);
- emoji only where meaningful, one per line; action buttons get an action icon (📥 Install, 🗑 Delete, ✖️ Cancel,
  ◀️ Back), list buttons (module or key names) none;
- built-in commands set `@command(emoji=...)` for `.help` and the command reference;
- long text and tracebacks in `utils.quote(..., expandable=True)`, code in `<pre>`.

## Plans and constraints

Roadmap: local `ROADMAP.md` (gitignored, not on GitHub; done items `[x]`). Principles affecting code:
- small core: built-in modules (`uroboros/modules/`) use only the public API, like third-party ones;
- plain Telethon 1.x only: no forks, no Telethon 2 before its stable release;
- new dependencies must install in Termux without compiling (exception: aiogram 3, whose `pydantic-core` builds
  with Rust; the user decided that).

**Hikka adapter (`hikka/`).** `hikka.is_hikka` detects a module, `check_supported` rejects Hikka internals. Modules
run with `__package__ = uroboros.hikka.modules`, so `from .. import loader, utils` gets the shims in
`uroboros/hikka/`. `hikka.loader.Module.__init_subclass__` translates Hikka markers (`is_command`, `cmd`/`watcher`/
`_inline_handler` suffixes, `InfiniteLoop`) into Uroboros decorator attributes; `_bind` (a loader hook) swaps `db`
for a Hikka-style DB and `inline` for `HikkaInline`. `hikkatl` → Telethon: `hikka/aliases.py`. Compat table:
`scripts/hikka_compat.py` (executes third-party code: run isolated only).

**Source scan (`scan.py`).** AST heuristics before install: `Loader.install` raises `scan.UnsafeModuleError` on
dangerous code unless `force=True` (confirm button or `-f` in `.dlm`/`.lm`/`.uplm`/`.restore`); suspicious findings
are shown in replies. Built-ins aren't scanned. The loader stores sha256 of third-party files (DB
`uroboros.loader`/`hashes`): if a file changed outside Uroboros and contains dangerous code, `load_all` skips it.
`.uplm` shows a `difflib` diff and waits for confirmation (`-f` skips). GitHub modules are fetched by commit
(`github.pin`: SHA via API, falling back to the original URL); `installed` keeps the original URL for updates,
`pins` the pinned one.

**Runtime guard (`guard.py`).** `Guard` (`loader.guard`) restricts third-party modules except trusted ones
(`uroboros.loader`/`trusted`: installed with confirmed dangerous code, or `.security trust`):
`UroborosClient.__call__` blocks dangerous requests (`BLOCKED_REQUESTS`), the `UroborosClient.session` property hides
the session from code in `uroboros.ext.*`/`uroboros.lib.*`/Hikka modules (via `sys._getframe`), and an audit hook
(`guard.activate`, installed in `main.run`) prevents opening/deleting the session, `config.json` and `uroboros.db`
or passing them to commands while `current_module` is set. Blocking raises `ModuleBlocked` (`LoadError` and
`PermissionError`) and notifies Saved Messages. Not a sandbox. Hikka modules won't load without the adapter.

## Branches and versions

- **All work happens in `dev`.** Commit and push only there; never commit to `master` directly (a hook blocks it).
- **`master` is updated only by merging `dev`**, after local checks (`ruff check`, `ruff format --check`, `pytest`)
  and the user's **explicit approval** of that merge. Procedure: `/promote`.
- **Version depends on the branch:** `X.Y.Z-dev` in `dev`, `X.Y.Z` in `master` (same in `pyproject.toml` and
  `uroboros/__init__.py`; pip normalizes `-dev` to `.dev0`). The suffix is dropped in the merge commit.
  `tests/test_version.py` checks this per branch.
- pip installs (no git) update from PyPI: `updater.check_pip`/`install_pip`; `stable` channel = versions without a
  suffix, `beta` = also `.devN`; `.dev` isn't available there.
- `.update beta` follows the bot's branch, so `dev` and `master` update independently. `.dev on`/`.dev off`
  (`updater.prepare_switch`/`switch`) switch the branch with rollback if the new one doesn't start.
- **Releases** (tags, GitHub releases) only when the user asks, only from `master` after `/promote`: tag `vX.Y.Z`,
  `gh release create` with English notes (`/release`); the release publishes `uroboros-userbot` to PyPI
  (`publish.yml`). Confirm the version number with the user. Old tags `v0.1.0b1`, `v0.1.0b2`, `v0.1.1b2` and
  `v*-dev` followed earlier rules.
