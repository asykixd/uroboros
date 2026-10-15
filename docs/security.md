# Security

A userbot acts as your account, so Uroboros guards it on three fronts: who can run commands, what code can be
installed, and what that code can do at runtime.

This is not a sandbox. Third-party modules run in the bot's process, and a determined author can get around the
checks. They stop typical malicious code and accidents, not arbitrary Python. Install modules you trust.

## Who can run commands

Your own (outgoing) messages always. Commands in other people's messages run only if the sender has enough access:

| Level | Who | Default commands |
|---|---|---|
| `owner` | this account and users added with `.owner add` | everything, including `.e`, `.t`, `.dlm`, `.ulm`, `.restore`, `.update` |
| `sudo` | added with `.sudo add` | most commands |
| `support` | added with `.support add` | help, `.ping`, `.info` |
| `everyone` | anyone | only commands explicitly set to this level |

Each level includes the ones below it. Change a command's level with `.security <command> <level>`; reset with
`.security <command> default`. `.security` alone shows groups, overridden permissions, frozen and trusted modules.

## Code scanning on install

Before `.dlm`, `.lm`, `.uplm` and `.restore`, Uroboros reads the module source and looks for:

- session access: `client.session.save()`, `StringSession.save`, `auth_key`, `api_hash`, `.session` files,
  `uroboros.db`;
- account takeover requests: terminating sessions, deleting the account, changing 2FA or phone, QR login, logout,
  spending stars, transferring gifts;
- hidden code: `exec`/`eval` of `base64`, `zlib`, `marshal`;
- Uroboros system settings and protection: access rights, trusted modules, flood protection, inline bot token.

A module with dangerous code isn't installed until you confirm explicitly: the "Install anyway" button or `-f`
(`.dlm -f`, `.uplm -f`, `.restore -f`). This applies to modules from connected repos too.

Suspicious things (environment variables, shell commands, file deletion, `config.json`, `exec` of a string, channel
joins) are listed separately in the reply but don't block install.

A module can declare what it needs: `# meta permissions: network, files`. Permissions are shown before install, and
undeclared usage triggers a warning. See [Writing modules](modules.md#file-header).

## Module source and version

- Modules download over https only; redirects to http are rejected.
- A module from an unconnected source needs confirmation showing its origin and line count.
- So does the first module from each connected repo (the official one included). After that, clean modules from
  that repo install without a question. `.delrepo` forgets the approval.
- GitHub modules and libraries are pinned to a commit: the file is fetched by SHA, and the confirmation shows
  which commit.
- `.uplm` shows each module's and library's diff and updates after confirmation.
- A repo can publish `manifest.json` with the sha256 of each module. A downloaded file that doesn't match is
  refused; verified modules are marked 🔏. See [Writing modules](modules.md#install-time-scan).
- Uroboros stores sha256 of installed module files. If a file was changed outside Uroboros and now contains
  dangerous code, it won't load at startup.
- `# requires:` accepts only package names with versions: no URLs or pip options.

## Runtime protection

A third-party module can't:

- read `self.client.session`;
- open, delete or rename the session, `config.json` or `uroboros.db`, or pass them to shell commands;
- send requests that hijack the account or spend money (the same ones the install scan looks for);
- change Uroboros system settings in the database (`uroboros.*`: access levels, trusted modules, the bot token),
  read the inline bot token or dump the whole database.

This covers the module's top-level code and `__init__` too, and libraries it loads with `self.import_lib`.
The attempt raises `PermissionError`, nothing happens, and Saved Messages gets a notice naming the module and
the action. The last 100 blocks are also kept in the database: `.security log` shows them, newest first,
`.security log clear` empties the log.

Restrictions are lifted for a module whose dangerous code you confirmed on install, and for one you trust
explicitly: `.security trust <module>`. Revert with `.security untrust <module>`.

### Declared permissions

A module with a `# meta permissions:` header (or the short `# permissions:`) is held to it at runtime:

| Permission | Blocked when not declared |
| --- | --- |
| `network` | opening sockets: `socket.connect`, `sendto`, `bind` (so `aiohttp`, `requests`, `urllib` too) |
| `files` | opening, creating, deleting, renaming and listing files. Reading Python's own files (stdlib, site-packages, time zones) and imports are allowed |
| `processes` | starting processes: `subprocess`, `os.system`, `os.exec*`, `os.fork` |

`env` and `exec` are only checked by the install scan: Python has no reliable runtime hook for them.

What the core does for the module doesn't count: Telegram traffic through `self.client`, the inline bot,
downloading libraries, `# requires:` installs. Files a module sends through Telethon (`send_file` with a path) do
count. Modules without the header behave as before, and trusted modules aren't limited. It's a heuristic like the
rest of the runtime protection: code run in threads or in tasks spawned by libraries may be attributed to nobody, in
which case network access is allowed and file and process access is blocked.

## Flood protection

Telegram requests from third-party modules are counted. A module that sends too many (default: more than 60 in
30 seconds) is frozen for 5 minutes and you get notified. Configure with
`.security flood <requests> <seconds> <freeze>`, disable with `.security flood off`, unfreeze with
`.security unfreeze <module>`.

## Data

The session, `config.json` (api_id and api_hash) and the database live in `data/`. That's access to your account:
never publish or share this folder. `.backup` saves the database and modules, but not the session or `config.json`.
A backup does contain the inline bot token and module settings, so don't forward it.

`.backup auto <hours> [keep]` sends a backup on a schedule (off by default) to Saved Messages, or to the chat set
in `.cfg backup chat`: pick only a chat nobody else can read. The bot deletes its own autobackups beyond the last
`keep` (5 by default, 0 keeps all); backups sent by hand are never deleted.

A backup records the account it was made on. `.restore` of a backup from another account (or from an older
version without that record) asks for confirmation (`.restore -f`) and keeps your access levels, trusted modules
and inline bot. After a restore the database ignores writes until the restart, so running modules can't overwrite
the restored values.
