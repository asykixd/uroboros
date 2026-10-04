# Hikka and FTG modules

Uroboros loads Hikka and FTG modules unchanged: `.dlm` and `.lm` recognize them (`from .. import loader, utils`,
`loader.Module`, `@loader.tds`, `hikkatl`) and load them through the adapter.

## How it works

A Hikka module runs as a submodule of `uroboros.hikka.modules`, so its `from .. import loader, utils` gets the
Uroboros shims:

- `loader`: `Module`, `Library`, decorators `command`, `watcher`, `inline_handler`, `callback_handler`, `loop`,
  `tag`, `raw_handler`, access `owner`, `sudo`, `support`, `unrestricted`, `ModuleConfig`, `ConfigValue`,
  `validators`, `StopLoop`, `SelfUnload`;
- `utils`: `answer`, `answer_file`, `get_args*`, `get_chat_id`, `get_target`, `get_user`, `escape_html`, `run_sync`,
  `get_link`, `chunks`, `rand`, `smart_split`, `remove_html`, `mime_type`, module service chats `asset_channel`,
  `dnd`, `invite_inline_bot`, `set_avatar` and more;
- `validators`: all Hikka validators;
- `inline.types`: `InlineCall`, `InlineQuery`, `InlineMessage`;
- `database` (`Database` for annotations), `version`, `main`, `security`, `types`: the few bits modules reference.

`import hikkatl...` (Hikka's Telethon fork) and `herokutl` (Heroku's) resolve to plain Telethon. Modules with
`# scope: hikka_only` load: it means "needs Hikka, not FTG".

Mapping:

| Hikka | Uroboros |
|---|---|
| `xxxcmd` and `@loader.command(ru_doc=..., alias=...)` | command with description and aliases |
| `@loader.watcher(only_pm=True, no_commands=True, ...)` | watcher filtered by Hikka tags |
| `@loader.loop(interval, autostart)` | `@loop`, `self.<method>.start()/stop()/status` |
| `client_ready(client, db)`, `on_dlmod(client, db)` | called after load and on first install |
| `strings` + `strings_ru` | `self.strings("key")` (Russian strings preferred for now) |
| `self.get` / `self.set`, `self.db.get(owner, key)` | same storage, module data under the class name, as in Hikka |
| `self.inline.form(text, message, reply_markup=...)`, `list`, `gallery` | Uroboros inline bot forms |
| `@loader.owner`, `@loader.sudo`, `@loader.support`, `@loader.unrestricted` | `.security` access levels |

Hikka module commands are owner-only by default, as in Hikka.

## Not supported

Such modules fail at load with a clear error instead of breaking mid-run:

- Hikka internals: `from ..tl_cache`, `from .._internal`, `from .. import translations` and any submodule not
  listed above;
- `import hikka` and Hikka's Pyrogram client (`hikkapyro`, `pyrogram`);
- modules with `# scope: hikka_min` newer than 1.6.3.

Partially supported:

- Hikka group permissions (`@loader.group_admin`, `@loader.group_member`, `@loader.pm`): the command is owner-only;
- `self.request_join`: Uroboros doesn't join channels for modules, returns `False`;
- `db.pointer` and `self.pointer` return plain values, not live lists and dicts: save changes with `set`;
- `self.invoke`, `utils.asset_forum_topic` (Heroku fork only): error on call;
- Hikka-TL features beyond Telethon (e.g. `client.hikka_me`) are unavailable.

## Compatibility table

[hikka-compat.md](hikka-compat.md) is built by `scripts/hikka_compat.py`: it downloads modules from popular repos
and tries to load them. The script executes third-party code, so run it isolated, e.g. manually via GitHub Actions
(the "Hikka compatibility" workflow); the table comes as an artifact.
