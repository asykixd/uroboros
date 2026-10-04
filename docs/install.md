# Install

Uroboros runs anywhere with Python 3.10+. On first run it prints a link to the web login panel: enter `api_id` and
`api_hash` (from https://my.telegram.org/apps), phone, code and 2FA password, or scan a QR code. Console login:
`--cli`.

Data lives in `data/` next to the program (override with `UROBOROS_DATA`). It contains the Telegram session, which
is full access to your account: never share it.

## Options

| Option | Description |
|---|---|
| `--cli` | log in from the console instead of the web panel |
| `--host`, `--port` | web panel address (default `127.0.0.1:8080`), or `UROBOROS_WEB_HOST`, `UROBOROS_WEB_PORT` |
| `UROBOROS_DATA` | data directory (default `./data`) |
| `UROBOROS_API_ID`, `UROBOROS_API_HASH` | Telegram app credentials instead of `config.json` |
| `UROBOROS_BOT_TOKEN` | your own inline bot instead of an auto-created one |

## Updating

`.update` fetches the channel, shows the changelog and asks to confirm (`.update -f` skips confirmation). The new
version is installed with its dependencies; if they fail or the new version doesn't start, git rolls back and the
bot keeps running.

- `.update channel beta`: every commit on the bot's branch (default); `master` is stable, `dev` is development;
- `.update channel stable`: releases (tags) only;
- `.update notify off`: no daily new-version notice.

pip installs update from PyPI: `stable` gets releases, `beta` also gets `.devN` builds. Rollback works the same way.

Branches:

- `.dev`: current branch and version;
- `.dev on`: switch to `dev` builds (new features before testing, `-dev` versions);
- `.dev off`: back to stable `master`.

The bot shows the target version and asks to confirm (`-f` skips). If the new branch's dependencies fail or it
doesn't start, the bot returns to the previous branch. In Docker the branch is chosen at image build time.

## pip

No git or install scripts, any OS with Python 3.10+:

```bash
python3 -m venv uroboros
uroboros/bin/pip install uroboros-userbot
cd uroboros && bin/uroboros
```

Data goes to `uroboros/data`. Update with `.update` (from PyPI). Branches aren't available here: install from git
for `dev` builds.

## Linux and VPS

```bash
curl -fsSL https://raw.githubusercontent.com/asykixd/uroboros/master/install.sh | sh
```

The script checks Python and git, clones the repo to `~/uroboros` (override with `UROBOROS_DIR`), creates a
virtualenv and starts the bot. Debian/Ubuntu may need `sudo apt install git python3 python3-venv`.

On a headless VPS, open the login panel through an SSH tunnel from your computer:

```bash
ssh -L 8080:127.0.0.1:8080 user@server
```

then open the link from the console in your local browser.

### systemd service

```bash
sh ~/uroboros/install.sh --service
```

Installs the `uroboros` user service. Log in manually first (`cd ~/uroboros && .venv/bin/python -m uroboros`), then:

```bash
systemctl --user enable --now uroboros
journalctl --user -u uroboros -f
sudo loginctl enable-linger $USER
```

The last command keeps the service running when you're logged out. `.restart` and `.update` restart the process in
place; systemd is fine with that.

## Termux (Android)

```bash
curl -fsSL https://raw.githubusercontent.com/asykixd/uroboros/master/install.sh | sh
```

In Termux the script installs `python`, `git` and `rust`: Rust builds `pydantic-core` for the inline bot, which
takes a few minutes. Open the login panel in a browser on the same phone.

Autostart on boot via [Termux:Boot](https://f-droid.org/packages/com.termux.boot/):

```bash
sh ~/uroboros/install.sh --boot
```

Termux:Boot starts the bot without a terminal, so log in manually first.

## Docker

```bash
git clone https://github.com/asykixd/uroboros && cd uroboros
docker compose up -d
docker compose logs -f
```

The login link appears in the logs; the panel is reachable only from this machine (`127.0.0.1:8080`). Data is in
`./data`. Update with `git pull && docker compose up -d --build` (`.update` doesn't work in Docker).

## Windows

1. Install [Python 3.10+](https://www.python.org/downloads/) (check "Add python.exe to PATH") and
   [Git](https://git-scm.com/download/win).
2. In PowerShell:

```powershell
git clone https://github.com/asykixd/uroboros
cd uroboros
python -m venv .venv
.venv\Scripts\python -m pip install -e .
.venv\Scripts\python -m uroboros
```

Open the link from the console in a browser. Keep the console window open: `.restart` and `.update` restart the bot
in it.

## macOS

```bash
brew install python git
curl -fsSL https://raw.githubusercontent.com/asykixd/uroboros/master/install.sh | sh
```

Or manually, as on Linux: `git clone`, `python3 -m venv .venv`, `.venv/bin/pip install -e .`,
`.venv/bin/python -m uroboros`.
