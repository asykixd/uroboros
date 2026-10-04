<p align="center">
  <img src="https://raw.githubusercontent.com/asykixd/uroboros/master/docs/assets/logo.svg" width="112" alt="Uroboros">
</p>

<h1 align="center">Uroboros</h1>

<p align="center">
  Modular Telegram userbot on Python and Telethon.<br>
  One-command modules, inline buttons and forms, account protection from malicious code.
</p>

<p align="center">
  <a href="https://github.com/asykixd/uroboros/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/asykixd/uroboros/ci.yml?branch=master&label=tests&style=flat-square" alt="Tests"></a>
  <a href="https://pypi.org/project/uroboros-userbot/"><img src="https://img.shields.io/pypi/v/uroboros-userbot?style=flat-square&color=14b8a6" alt="PyPI"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-14b8a6?style=flat-square&logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/telethon-1.x-0f766e?style=flat-square" alt="Telethon 1.x">
  <a href="https://github.com/asykixd/uroboros/blob/master/LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0-2dd4bf?style=flat-square" alt="AGPL-3.0"></a>
</p>

<p align="center">
  <a href="https://asykixd.github.io/uroboros/"><b>Docs</b></a> ·
  <a href="https://asykixd.github.io/uroboros/install/"><b>Install</b></a> ·
  <a href="https://asykixd.github.io/uroboros/commands/"><b>Commands</b></a> ·
  <a href="https://asykixd.github.io/uroboros/modules/"><b>Writing modules</b></a> ·
  <a href="https://github.com/asykixd/uroboros-modules"><b>Modules</b></a> ·
  <a href="https://github.com/asykixd/uroboros/blob/master/README.ru.md"><b>Русский</b></a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/asykixd/uroboros/master/docs/assets/preview.svg" width="720" alt="Uroboros messages in Telegram">
</p>

> [!NOTE]
> The bot interface is in Russian for now; English is coming.

## Features

- 📦 **One-command modules**: `.dlm notes`, `.search`, custom repos via `.addrepo`
- 🛡 **Account protection**: modules are scanned before install and can't reach the session at runtime
- 🤖 **Buttons and forms**: built-in inline bot for settings, help and confirmations
- 🔁 **Hikka and FTG modules**: loaded as-is through an adapter ([details](https://asykixd.github.io/uroboros/hikka/))
- 🌿 **Stable and dev channels**: `.dev on`/`off`, `.update` with rollback
- 🔐 **Access levels**: `owner`, `sudo`, `support`, per-command permissions
- 💾 **Backups**: database and modules in one archive, scheduled
- 🐧 **Runs anywhere**: Linux/VPS, Termux, Docker, Windows, macOS

## Install

Linux, VPS, Termux, macOS:

```bash
curl -fsSL https://raw.githubusercontent.com/asykixd/uroboros/master/install.sh | sh
```

Or `pip install uroboros-userbot`. Docker, systemd, Termux autostart and Windows: see
[install docs](https://asykixd.github.io/uroboros/install/).

On first run Uroboros prints a link to a web login panel: enter `api_id`/`api_hash` from
[my.telegram.org/apps](https://my.telegram.org/apps), phone, code and 2FA password, or scan a QR code. The panel
shuts down after login, and Uroboros creates its inline bot via @BotFather. Console login: `--cli`.

## Main commands

| Command | Description |
|---|---|
| `.help [module]` | modules and help |
| `.dlm <url \| owner/repo/module \| module>` | install a module; `.dlm owner/repo` lists a repo |
| `.uplm [module]` | update modules (shows diff, asks to confirm) |
| `.ulm <module>` | remove a module |
| `.cfg [module]` | module settings, with buttons |
| `.update` | update Uroboros with changelog and rollback |
| `.dev on \| off` | switch to `dev` builds or back to `master` |
| `.security` | access, command permissions, flood and module protection |
| `.backup`, `.restore` | backup and restore |
| `.info`, `.ping`, `.logs` | bot status |

Full list with access levels: [command reference](https://asykixd.github.io/uroboros/commands/).

## Writing a module

```python
# meta developer: @you
# meta permissions: none
# requires_uroboros: 1.0
from uroboros import Module, command, utils


class Notes(Module):
    """Notes"""

    @command("save", emoji="💾")
    async def save(self, message):
        """<name> <text> — save a note"""
        name, _, text = utils.get_args_raw(message).partition(" ")
        self.set(name, text)
        await utils.answer(
            message,
            utils.card(
                "✅ <b>Note saved</b>",
                [f"🏷 Name: <code>{utils.escape_html(name)}</code>", f"📏 Length: <code>{len(text)}</code>"],
                hint=f"show: <code>.note {utils.escape_html(name)}</code>",
            ),
        )
```

Modules get `self.client` (Telethon), storage (`self.get`/`self.set`), `self.config`, command filters, watchers,
`@loop` tasks, libraries, inline forms (`self.inline.form(...)`) and `utils` helpers. See the
[module guide](https://asykixd.github.io/uroboros/modules/); ready-made modules and a repo template:
[uroboros-modules](https://github.com/asykixd/uroboros-modules).

## Security

> [!WARNING]
> A userbot acts as your account. Spam, mass messaging and request floods can get it banned: test on a spare
> account first.

Third-party modules run in the bot's process. Uroboros scans their code on install, shows permissions and diffs,
pins GitHub modules to a commit and blocks access to the session. It is not a sandbox: install modules you trust.
See [security](https://asykixd.github.io/uroboros/security/).

## Development

`dev` is the development branch (`X.Y.Z-dev`), `master` is stable.

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev,docs]'
.venv/bin/python -m pytest
.venv/bin/mkdocs serve
```

## Credits

The module API and adapter follow [Hikka](https://github.com/hikariatama/Hikka) (AGPL-3.0); thanks to its authors.
Built on [Telethon](https://github.com/LonamiWebs/Telethon) and [aiogram](https://github.com/aiogram/aiogram).

## License

AGPL-3.0, see [LICENSE](https://github.com/asykixd/uroboros/blob/master/LICENSE).
[Contributing](https://github.com/asykixd/uroboros/blob/master/CONTRIBUTING.md) ·
[Security policy](https://github.com/asykixd/uroboros/blob/master/SECURITY.md)
