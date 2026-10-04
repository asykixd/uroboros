# Roadmap

Versions are approximate: order matters more than numbers. `[x]` is done.

## Principles

- **Small core, everything else is modules.** Built-in commands use the same public API as third-party ones.
- **Hikka-like API**, so the compatibility adapter stays a thin layer.
- **Plain Telethon 1.x.** No fork; Telethon 2 only after its stable release.
- **Runs anywhere with Python 3.10+:** Linux/VPS, Termux, Windows, macOS. New dependencies must install in Termux
  without compiling. Exception: aiogram 3 (`pydantic-core` builds with Rust, `pkg install rust`).
- **English first.** Repo and docs are in English with a Russian version; the bot interface is Russian for now.
- Branches: `dev` (`X.Y.Z-dev`) for development, `master` (`X.Y.Z`) stable, updated only by merging `dev`.

---

## 0.1 Core ✅ `v0.1.0b1`

- [x] Console login, config in `data/`, environment variables
- [x] Cached SQLite key-value store (`db.get`/`db.set`, as in Hikka)
- [x] Loader: `exec` of source, per-file unload, rollback on `on_load` failure; `# requires:` → `pip install`
- [x] Dispatcher: prefix, user aliases, watchers, errors in replies
- [x] `Module`, `@command`, `@watcher`, `ModuleConfig`/`ConfigValue`, validators
- [x] GitHub install: URLs, `owner/repo/module`, repo listing, connected repos
- [x] Built-in modules: help, loader, settings, config, eval, system
- [x] Restart and `.update` via git; core tests (offline)

## 0.1.x Stabilization ✅ `v0.1.0b2`, `v0.1.1b2`

- [x] CI: pytest on Python 3.10–3.13, Linux, macOS, Windows; ruff
- [x] Clean shutdown (`unload_all()` on exit and restart)
- [x] `FloodWaitError` handling in `utils.answer` and the dispatcher
- [x] Windows restart via a supervisor process
- [x] `.logs [level]` to Saved Messages, log rotation
- [x] `.backup`/`.restore` (database and modules, no session)
- [x] `.uplm [module]`
- [x] Lock file against running twice with one session

## 0.2 Module API ✅

- [x] `@loop` background tasks, stopped on unload
- [x] Auto-removal of handlers added via `self.client.add_event_handler`
- [x] `self.get`/`self.set`
- [x] Command filters: `only_pm`, `only_groups`, `chats=[...]`, `no_reply`, etc.
- [x] Header metadata: `# meta ...`, `# requires_uroboros` with a core version check
- [x] Libraries (`self.import_lib(url)`) with reference counting
- [x] `self.strings("key", **kw)` with HTML escaping
- [x] `utils`: `get_user`, `get_target`, `get_chat_id`, `get_reply`, `run_sync`, `answer_file`
- [x] `on_dlmod` hook; docs and examples

## 0.3 Inline bot ✅

- [x] aiogram 3 bot in the userbot process, auto-created via @BotFather (or `.inlinebot`, `UROBOROS_BOT_TOKEN`)
- [x] `self.inline.form`, `list`, `gallery`; buttons with callbacks, text input, confirmation
- [x] `@inline_handler`, `@callback_handler`
- [x] Inline versions of `.cfg`, `.help`, `.ulm` confirmation
- [x] Verified in Termux (`pydantic-core` via `pkg install rust`) and on a live account

## 0.4 Access and security ✅

- [x] `owner`, `sudo`, `support` groups; per-command permissions (`.security <command> <level>`)
- [x] Commands from other users only with granted access; `.e`, `.t`, `.dlm`, `.ulm` owner-only
- [x] Flood protection: freeze modules that send too many requests
- [x] Confirmation for modules from unconnected sources
- [x] Install-time scan (`.dlm`, `.uplm`, `.restore`): dangerous code blocked until confirmed (`-f`)
- [x] `# requires:` limited to package names; https-only downloads
- [x] Runtime protection: no access to the session, `data/` files or account-threatening requests
- [x] `.uplm` shows diffs; sha256 of installed files; GitHub modules pinned to a commit
- [x] `# meta permissions` checked against the code

## 0.5 Web login panel ✅

- [x] aiohttp server only when there's no session; shuts down after login
- [x] api_id/api_hash → phone → code → 2FA, or QR code
- [x] One-time token in the link, `127.0.0.1` by default, SSH tunnel instructions; `--cli` fallback

## 0.6 Hikka adapter ✅

- [x] Detect Hikka modules; shims for `hikkatl` → `telethon`, `loader`, `utils`, `..inline.types`
- [x] Hikka `Module`, decorators, `xxxcmd`, `client_ready`, config, validators, `strings_ru`, `utils.*`
- [x] `self.inline.form` and `@loader.inline_handler` on the inline bot; Hikka access decorators
- [x] Compatibility suite `scripts/hikka_compat.py` (isolated run moved to 1.1)
- [x] Clear errors for unsupported features ([docs](docs/hikka.md))

## 0.7 Install and operations ✅

- [x] `install.sh` for Linux and Termux; systemd user service; Termux:Boot
- [x] Docker image and `docker-compose.yml`
- [x] Windows and macOS instructions ([docs](docs/install.md))
- [x] `stable`/`beta` channels, changelog before update, daily new-version notice
- [x] Scheduled backups (`.cfg backup interval 24`)
- [x] `.dev on`/`.dev off` with rollback

## 1.0 Stable ✅ `v1.0.0`

- [x] Frozen module API: semver, deprecation policy ([docs](docs/stability.md)), `tests/api_snapshot.json`
- [x] mkdocs site on GitHub Pages; command reference and examples generated from code
- [x] Official [`uroboros-modules`](https://github.com/asykixd/uroboros-modules) repo (connected by default) and
  repo template
- [x] `.search` across connected repos
- [x] PyPI package `uroboros-userbot`, `.update` from PyPI, publishing from GitHub releases
- [x] Test coverage of loader, dispatcher, adapter and inline layer

---

## 1.1 Reliability and module authoring

### Localization
- [ ] English bot interface, Russian kept as an option (`.lang`); `strings_<lang>` for modules

### Compatibility
- [ ] Run the Hikka compatibility suite in isolation (Actions or Docker without network, with limits) and fix common
  failures

### Reliability
- [ ] Safe mode: after repeated startup crashes load only built-in modules and report the culprit; `--safe`
- [ ] `.rollback <module>`: restore one of the last 2–3 versions (`data/modules/.history/`)
- [ ] `.status`: uptime, memory, frozen modules, `@loop` state, inline bot error, recent `FloodWait`
- [ ] `.report`: versions, modules and last traceback in one message for an issue

### Module API
- [ ] Typed command arguments: `@command(args="<user> [reason...]")` with parsing, user lookup, errors and `.help`
- [ ] `await self.inline.ask(message, "Question?", ["Yes", "No"])` returning the answer to the command
- [ ] `@cron("0 9 * * *")` scheduled tasks that survive restarts
- [ ] Module data migrations: `db_version = 2` and `on_migrate(old)`
- [ ] `uroboros.testing`: public client, message and inline stubs for testing modules without Telegram

### Tools
- [ ] Hot reload of a local modules folder (`--dev`)
- [ ] `uroboros new <name>` scaffold; `uroboros check module.py` API check and minimum `requires_uroboros` hint

### Small things
- [ ] "Did you mean `.dlm`?" on command typos
- [ ] `.help <module>`: description, author, version, install source

## Ideas

- Multiple accounts in one process
- Telethon 2 once stable (with a compatibility layer for modules)
- Module catalog with ratings and review
- Persistent web control panel
- Own Telethon fork

## Risks

| Risk | Mitigation |
|---|---|
| aiogram 3 / pydantic-core in Termux | Builds with `pkg install rust`, documented |
| Hikka modules depend on Hikka-TL | Compatibility table, unsupported features rejected explicitly |
| Account bans for flooding | Flood protection, warning in README |
| Telethon 1.x end of support | Keep Telethon exposure in the module API minimal |
