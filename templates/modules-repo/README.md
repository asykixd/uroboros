# your-modules

Modules for [Uroboros](https://github.com/asykixd/uroboros), a modular Telegram userbot.

## Install

In any chat:

```
.dlm your-username/your-modules          # list the modules in this repo
.dlm your-username/your-modules/hello    # install one
.addrepo your-username/your-modules     # connect the repo once...
.dlm hello                               # ...then install by name
```

## Layout

| Path | What it is |
| --- | --- |
| `*.py` in the root | Modules. Every root `.py` file is listed by `.dlm owner/repo`; names starting with `_` are skipped. |
| `libs/` | Libraries (`Library` subclasses) loaded with `self.import_lib(url)`; not listed as modules. |
| `manifest.json` | Repo name, author and module descriptions. Uroboros doesn't read it yet; keep it up to date for indexes. |
| `tools/check_modules.py` | Scans and loads every module the way Uroboros does on install. |
| `.github/workflows/check.yml` | Runs the check on every push, pull request and weekly against the latest Uroboros. |

## Writing modules

Start from `hello.py`. The API is documented at
[asykixd.github.io/uroboros/modules](https://asykixd.github.io/uroboros/modules/). Keep the file header up to date:

```python
# meta developer: @your_username
# meta version: 1.0
# meta permissions: none
# requires_uroboros: 1.0
```

## Check locally

```bash
python3 -m venv .venv && .venv/bin/pip install uroboros-userbot
.venv/bin/python tools/check_modules.py
```

The check fails on load errors and on code the install-time scan marks as dangerous; suspicious code is printed as a
warning. It needs no Telegram account.
