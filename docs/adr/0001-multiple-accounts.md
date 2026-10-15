# ADR 0001: multiple Telegram accounts

- **Status:** proposed
- **Date:** 2026-10-16
- **Scope:** design only, nothing is implemented by this ADR

## Context

Users ask to run several Telegram accounts with one Uroboros install. Today one process serves one account: one
data directory (`UROBOROS_DATA`, default `./data`) holds `config.json`, the session, `uroboros.db`, `modules/`,
the log and `uroboros.lock`. Two processes with different data directories already work side by side; they just
have to be started and supervised separately (two systemd units, two Termux:Boot scripts, two containers).

Two ways to make this a first-class feature:

- **A. One process, several clients.** `main.run` starts one `UroborosClient`, `Database`, `Loader`,
  `Dispatcher` and `InlineManager` per account in the same event loop.
- **B. One supervisor, one child process per data directory.** A small parent process starts
  `python -m uroboros` once per configured data directory and restarts children that exit.

## What A would have to change

The core assumes one account per process in several places:

| Place | Assumption |
|---|---|
| `loader.py` | Built-in modules are registered in `sys.modules` as `uroboros.modules.<stem>`, a fixed name. A second `Loader` would overwrite the first one's entries and unload them on its own reload. |
| `guard.py` | `activate` keeps one active `Guard` per process for the audit hook. The hook protects one data directory: the second account's session, config and DB would be unprotected, or one guard would have to know every account. |
| `ratelimit.current_module` | Context is per task, so it works, but any code path that forgets `module_context` attributes requests to the wrong account's limiter. |
| `utils.restart` / `main.main` | Restart is `os.execv` of the whole process (a supervisor child on Windows): restarting one account restarts all of them. `.update` and `.dev on/off` are per process too. |
| `logs.setup` | One log file per process; `.logs` would mix accounts or need per-account handlers and filters. |
| `hikka/aliases.install` | Installs Hikka shims into `sys.modules` process-wide; fine to share, but Hikka modules of both accounts would share module-level state. |
| `InstanceLock` | One lock per data directory: fine, but a crash or a hung `on_unload` in one account takes all of them down. |

Security is the larger problem. The runtime guard is explicitly "not a sandbox": third-party module code runs in
the same interpreter as the core. In one process, a module installed on account A can reach account B through
`gc`, `sys.modules` or the event loop's tasks and read B's client or session. The user may have installed that
module only on A, trusting it with A only. Separate processes keep that boundary at the OS level (same user, but
no shared memory; the guard of each process protects its own files).

## What B needs

Almost nothing in the core changes, because one process per data directory is what already works:

- a `--data DIR` flag next to `UROBOROS_DATA` (convenience; the env var already works);
- a supervisor entry point, for example `python -m uroboros --accounts data/main data/work`, or a list in a small
  `accounts.json`;
- the supervisor starts one child per directory with `UROBOROS_DATA` set, restarts a child that exits with an
  error after a backoff, and stops all children on SIGTERM/Ctrl+C;
- first login: each child without a session opens the web login panel, so the supervisor assigns a distinct port
  per child (`UROBOROS_WEB_PORT`, base port + index) and prints which link belongs to which account;
- logs stay per data directory; the supervisor prefixes child stdout with the account directory name.

Restart and update keep working: on POSIX a child replaces itself with `os.execv`; on Windows the existing
`supervise` loop already restarts on exit code 75 and can run once per child. `.update` in one account updates the
shared code on disk; other accounts pick it up on their next restart, which the update notice can mention.

## Comparison

| | A: one process | B: supervisor + processes |
|---|---|---|
| Isolation between accounts | none (shared interpreter) | process boundary |
| Core changes | large: loader names, guard, restart, logs, every `self.loader.*` user | small: a flag and a supervisor |
| Crash or hang in one account | affects all | affects one |
| Memory (Termux matters) | lowest: one interpreter, one Telethon/aiogram import | one interpreter per account (estimate, not measured: +50–100 MB each) |
| Restart / update one account | not possible without a large refactor | works as today |
| Module API | must stay one-account; risk of cross-account leaks | unchanged |
| Inline bot | one bot per account anyway | one bot per account |

## Decision

Recommend **B: one supervisor with one child process per `UROBOROS_DATA` directory.**

It keeps the security model honest (third-party code of one account can't reach another account's session), needs
no changes to the module API or the loader, and reuses restart, update and locking as they are. The cost is memory
per account, which is acceptable for the expected two or three accounts; users on very small devices can keep
running a single account.

## Consequences

- Implementation, when scheduled: `--data`, `--accounts` (or `accounts.json`), port assignment for first login,
  child restart with backoff, docs in `install{,.ru}.md` and the systemd/Termux examples in `deploy/`.
- Option A stays rejected unless the guard becomes a real sandbox; revisit only then.
- Cross-account features (one command acting on several accounts) are out of scope; they would need an explicit
  IPC design of their own.
