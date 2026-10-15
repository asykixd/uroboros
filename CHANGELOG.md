# Changelog

Generated from Conventional Commits by `scripts/changelog.py`; don't edit by hand.

## Unreleased

### Features

- **templates:** add a module repo template with a ci check (1107923)
- **backup:** confirm foreign backups and keep account settings (829631c)

### Fixes

- **loader:** suggest .security trust with the module name (58e1de4)
- **main:** don't leak a coroutine when a block is reported off the event loop (48eb260)
- **web:** back off when a new QR code can't be fetched (47b809b)
- **updater:** keep the update channel and report rollback on failed .dev switch (9a0059c)
- **loops:** don't let a loop that swallows cancellation block unloading (e18f557)
- keep the bot running when module code calls sys.exit() (e9ab7d4)
- **inline:** keep the old bot until its replacement is ready (0941d83)
- **loader:** roll back failed updates and harden module loading (65eec3e)
- **loader:** scan libraries and require a trusted module for dangerous ones (632c2fa)
- **scan:** flag guard, trusted-list and session-key bypasses (430439c)
- **guard:** restrict module top-level code and constructors (bc5a65c)
- **guard:** block third-party modules from changing uroboros.* settings (734e030)
- **inline:** stop recreating the bot on every start after BotFather refused (f218805)

### Documentation

- describe the DB guard and backup ownership in CLAUDE.md (0e60e98)

### Tests

- cover module downloads and config loading (9ae3c17)
- close databases and files opened by tests (be1a8ac)

### CI and build

- publish the docker image to ghcr on release (770580e)
- enforce a minimum test coverage (e25b89c)
- type check uroboros with mypy (81424dc)
- audit dependencies with pip-audit (26ff0c5)
- pin the PyPI publish action to a commit (c680663)

### Chores

- ignore graphify output (3b79112)
- bump dev version to 1.1.0-dev (3fa1e14)

## Earlier

These releases predate Conventional Commits; their notes are on [GitHub Releases](https://github.com/asykixd/uroboros/releases).

- 1.0.1 (2026-10-09)
- 1.0.0 (2026-10-05)
- 0.1.1b2 (2026-10-03)
- 0.1.0b2 (2026-10-03)
- 0.1.0b1 (2026-10-03)
