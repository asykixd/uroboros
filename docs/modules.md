# Writing modules

A module is a `.py` file with one or more `Module` subclasses. Built-in modules use the same API, so their code is
a good reference: [`uroboros/modules/`](https://github.com/asykixd/uroboros/tree/master/uroboros/modules). More in
[examples](examples.md).

Install your module: send the file to any chat and reply to it with `.lm`, or use `.dlm <url>`.

## Minimal module

```python
from uroboros import Module, command, utils


class Hello(Module):
    """Says hello"""  # module description for .help

    @command("hello", aliases=["hi"])
    async def hello(self, message):
        """[name] — say hello"""  # command description for .help
        name = utils.get_args_raw(message) or "world"
        await utils.answer(message, f"Hello, <b>{utils.escape_html(name)}</b>!")
```

The module name is the class name (or the `name` attribute). All classes in one file are installed, updated and
removed together.

## File header

Comments at the top of the file are read before the code runs:

```python
# meta developer: @username
# meta version: 1.2
# meta permissions: network, files
# requires_uroboros: 0.2
# requires: requests pillow
```

| Line | Effect |
|---|---|
| `# meta <key>: <value>` | metadata; `developer` and `version` show in `.help module` |
| `# meta permissions: network, files` | what the module needs: `network`, `files`, `env` (environment variables), `processes` (shell commands), `exec` (executing code from strings), or `none`. Shown before install; undeclared usage triggers a warning |
| `# requires_uroboros: 0.2` | minimum core version. On older versions the module won't load and the user is told to update |
| `# requires: package ...` | pip packages, installed only if an import fails, one attempt |

## Lifecycle

| Method | When |
|---|---|
| `async on_load()` | after load: startup, install, update, `.reload`. If it raises, the module isn't loaded |
| `async on_dlmod()` | once, on first install, after `on_load`. Not on restart or update. If it raises, install is cancelled |
| `async on_unload()` | before unload: removal, update, `.reload`, stop and restart. On stop the client may already be disconnected |

Before `on_load` the loader sets:

- `self.client`: `TelegramClient` (Telethon 1.x);
- `self.db`: module storage;
- `self.config`: settings (if declared);
- `self.loader`: the loader (modules, commands);
- `self.inline`: inline bot forms (see [Inline bot](#inline-bot)).

`__init__` takes no arguments and these attributes aren't set yet. Only declare `self.config` there.

On unload the core stops `@loop` tasks, removes handlers added via `self.client.add_event_handler` or
`@self.client.on(...)`, and disables the module's form buttons.

## Commands

```python
@command("name", aliases=["n"], doc="description instead of docstring", emoji="🏷")
async def name(self, message): ...
```

Without a name the method name is used (a `cmd` suffix is dropped: `pingcmd` → `ping`). `emoji` is the command's
icon in `.help` and in the post-install command list (one, meaningful). Commands fire on your outgoing messages and
on messages from users with access (see [Access](#access)). Read arguments with `utils.get_args_raw(message)` (raw
string) or `utils.get_args(message)` (list, quote-aware).

If another module already owns the command name, install fails.

### Filters

```python
@command("ban", only_groups=True, only_reply=True)
```

| Filter | Command runs |
|---|---|
| `only_pm=True` | in private chats only |
| `only_groups=True` | in groups (and supergroups) only |
| `only_channels=True` | in channels only |
| `chats=[id, ...]` | in listed chats only (Telethon ids) |
| `only_reply=True` / `no_reply=True` | only as a reply / only not as a reply |
| `filter=lambda m: ...` | if the function returns `True` |

`only_pm`, `only_groups` and `only_channels` are mutually exclusive. If the message doesn't match, the command
isn't called and the user gets the reason. Restrictions show in `.help`.

### Access

```python
@command("note", access="support")
```

`access` is who besides this account may run the command: `owner`, `sudo` (default: sudo and owners), `support`
(support, sudo and owners) or `everyone`. Users manage groups with `.owner`, `.sudo`, `.support` and change any
command's level with `.security <command> <level>`. Commands that give access to the server or account (eval,
module install) should use `access="owner"`.

Telegram requests from third-party modules are counted. A module that sends too many (default: more than 60 in
30 seconds) is frozen for 5 minutes: its requests raise `ModuleFrozen` (a `LoadError`), and the user is notified in
Saved Messages. Configure with `.security flood`.

If another user ran the command, `message.out` is `False`: `utils.answer` replies instead of editing. Buttons on a
form sent in response to their command work for them too.

### Errors

Unhandled exceptions are shown to the user with a traceback. For expected errors ("no such user") raise
`LoadError("text")` from `uroboros.errors`: the user sees only the text. Long Telegram flood waits
(`FloodWaitError`) are reported by the dispatcher.

## Watchers

```python
from uroboros import watcher

@watcher(only_incoming=True, filter=lambda m: m.is_private)
async def watch(self, message): ...
```

Called for every new message (incoming and outgoing), concurrently. Options: `only_outgoing`, `only_incoming`,
`filter`. Exceptions are only logged.

## Background tasks

```python
from uroboros import loop

@loop(interval=60, autostart=True, wait_before=False)
async def refresh(self): ...
```

Runs every `interval` seconds. After load `self.refresh` is a controller: `self.refresh.start(interval=None)`,
`self.refresh.stop()`, `self.refresh.running`, `await self.refresh()` for an off-schedule call. An error in one run
is logged and doesn't stop the loop. `autostart=False`: don't start after `on_load`. `wait_before=True`: wait one
interval before the first run.

## Storage

```python
self.set("key", {"any": ["json value"]})
self.get("key", default)
self.db.delete("key")
```

Each module has its own storage (by module name). Values go through JSON: `tuple` comes back as `list`, dict keys
as strings. `get` returns a copy: call `set` to save changes. Storage is included in `.backup`.

## Config

```python
from uroboros import ConfigValue, ModuleConfig, validators

def __init__(self):
    self.config = ModuleConfig(
        ConfigValue("limit", 10, "How many to show", validators.Integer(minimum=1, maximum=100)),
        ConfigValue("mode", "fast", "Mode", validators.Choice(["fast", "slow"])),
    )

# in commands:
self.config["limit"]
```

Users change values with `.cfg module key value` and reset with `.rcfg`. User input arrives as a string; the
validator converts it.

| Validator | Accepts |
|---|---|
| `String(min_len=None, max_len=None)` | string |
| `Integer(minimum=None, maximum=None)` | integer |
| `Float()` | number |
| `Boolean()` | yes/no, true/false, 1/0, on/off |
| `Choice([...])` | one of the values |

A custom validator is any `value -> value` function that raises `validators.ValidationError` with a user-facing
message.

## Strings

```python
strings = {
    "done": "✅ Done: <b>{name}</b>",
}

self.strings("done", name=user_input)  # substitutions are HTML-escaped
self.strings["done"]                    # raw template
```

Templates may contain markup; substituted values are escaped. Wrap ready-made HTML in `utils.Html(...)`.

## Libraries

Share code between modules with a library:

```python
# textlib.py
from uroboros import Library

class TextLib(Library):
    async def on_load(self): ...
    async def on_unload(self): ...

    def shout(self, text):
        return text.upper()
```

```python
# in a module
async def on_load(self):
    self.textlib = await self.import_lib("https://github.com/you/repo/blob/main/textlib.py")
```

- `import_lib` returns the file's `Library` instance, or the Python module itself if there's none (a plain file of
  functions works).
- A library is loaded once and shared. It's unloaded with the last module that imported it.
- Source is cached on disk, so restarts don't need the network. `import_lib(url, reload=True)` re-downloads.
- A library has `self.client`, `self.loader` and its own `self.db`.

## Inline bot

An aiogram 3 bot runs alongside the userbot. On first run Uroboros creates it via @BotFather and enables inline
mode. Use your own with `.inlinebot <token>` or `UROBOROS_BOT_TOKEN`. Modules use it to show messages with buttons.

```python
@command("counter")
async def counter(self, message):
    """— counter with buttons"""
    await self.inline.form(message, "Count: 0", self._buttons(0))

def _buttons(self, value):
    return [
        [{"text": "−", "callback": self._add, "args": (value, -1)},
         {"text": "+", "callback": self._add, "args": (value, 1)}],
        [{"text": "✍️ Set", "input": "New value", "handler": self._typed}],
        [{"text": "Reset", "callback": self._add, "args": (0, 0), "confirm": "Reset the counter?"},
         {"text": "✖ Close", "action": "close"}],
    ]

async def _add(self, call, value, delta):
    value += delta
    await call.edit(f"Count: {value}", self._buttons(value))

async def _typed(self, call, text):
    if not text.lstrip("-").isdigit():
        await call.edit("❌ Integer required")
        return
    await call.edit(f"Count: {text}", self._buttons(int(text)))
```

`self.inline.form(message, text, buttons=None, *, photo=None, always_allow=())` replaces your command message with
a form and returns an `InlineMessage` with `edit(text, buttons)`, `delete()` and `unload()`. With `photo` (a URL),
`text` becomes the caption.

A button is a dict with `text` and one action:

| Key | Button action |
|---|---|
| `"callback": self.method` | calls `method(call, *args, **kwargs)`; arguments in `"args"` and `"kwargs"` |
| `"confirm": "Sure?"` | with `callback`: asks "Yes / Cancel" first |
| `"url": "https://..."` | opens a link |
| `"input": "hint", "handler": self.method` | text input: puts `@bot <id> ` into the input field, the user types a value and picks the result. Calls `method(call, text, *args)` |
| `"data": "string"` | plain callback button for `@callback_handler` (up to 64 bytes) |
| `"action": "close"` | deletes the form |

`buttons` is a list of rows, a single row (list of dicts) or a single button.

`call` (`InlineCall`) is a button press: `await call.edit(text, buttons)` updates the form (`buttons=None` removes
buttons, omitted keeps them), `await call.answer("text", show_alert=False)` shows a toast, `call.delete()` deletes
the form, `call.from_user` is who pressed, `call.query` is the aiogram `CallbackQuery`. If a callback raises
`LoadError`, the user sees its text in a popup.

Two more form types:

- `await self.inline.list(message, pages)`: text pages with ◀ ▶;
- `await self.inline.gallery(message, photos, caption="")`: images by URL. `photos` is a list (◀ ▶) or an async
  function returning a new URL ("More" button).

Only the account owner can press buttons; allow others with `always_allow=[id, ...]`. Forms live in memory: after a
restart old buttons answer "Button expired".

If the bot isn't running (no token, disabled via `.inlinebot off`), `form` raises `InlineError` from
`uroboros.errors` and the user sees why. Check in advance with `self.inline.available`. `InlineError` is also raised
when a chat forbids inline bots; built-in commands then fall back to plain text. For anything else there's
`self.inline.bot`, an `aiogram.Bot`.

### Inline commands and callbacks

```python
from uroboros import callback_handler, inline_handler

@inline_handler()
async def echo_inline_handler(self, query):
    """<text> — repeat"""
    return {"title": "Echo", "description": query.args, "message": utils.escape_html(query.args or "…")}

@callback_handler("vote:")
async def vote(self, call):
    await call.answer(f"Vote: {call.data.removeprefix('vote:')}")
```

- `@inline_handler(name=None)` answers `@bot <name> args` (default name: method name without `_inline_handler`).
  `query.args` is the text after the name. Return a dict or list of dicts with `title`, `description`, `message`
  (HTML), `buttons`, `photo`. An empty `@bot` query lists inline commands.
- `@callback_handler(prefix=None)` receives presses of `"data"` buttons starting with `prefix`.

## utils

| Function | Description |
|---|---|
| `await answer(message, text)` | reply to a command (HTML): edits your message, sends long text as a file |
| `await answer_file(message, file, caption=None)` | sends a file (replying to the same message as the command) and deletes the command message |
| `get_args_raw(message)` / `get_args(message)` | command arguments as string / list |
| `await get_reply(message)` | the replied-to message or `None` |
| `await get_user(message)` | message sender |
| `await get_target(message, arg=None)` | command target: replied message author → `@username`/id argument → private chat peer → `None` |
| `get_chat_id(message)` | chat id (Telethon format) |
| `await run_sync(func, *args, **kwargs)` | run a blocking function in a thread |
| `escape_html(text)` | HTML escaping |
| `quote(text, expandable=False)` | Telegram quote, `expandable` = collapsed |
| `card(title, body=None, hint=None, expandable=False)` | card reply: title, quoted body (string or list), 💡 hint |
| `Html(text)` | marks text as ready HTML for `escape_html` and `strings` |
| `get_prefix(db)` | current command prefix (`get_prefix(self.db.raw)`) |
| `format_duration(seconds)` | `3 д 04:05:06` |

## Reply style

Built-in modules reply with cards; use `utils.card` to match:

```python
await utils.answer(
    message,
    utils.card(
        "✅ <b>Note saved</b>",
        ["🏷 Name: <code>wifi</code>", "📏 Length: <code>12</code> chars"],
        hint="show: <code>.note wifi</code>",
    ),
)
```

```text
✅ Note saved
┃ 🏷 Name: wifi
┃ 📏 Length: 12 chars
💡 show: .note wifi
```

- the title starts with one status emoji: ✅ success, ❌ error, ⏳ in progress, ⚠️ warning;
- each body line gets one meaningful icon; no decorative emoji;
- put the next step in `hint`;
- long content: `utils.card(..., expandable=True)` or `utils.quote(..., expandable=True)`, code in `<pre>`;
- always pass user text through `utils.escape_html`;
- command icon for `.help`: `@command("note", emoji="📖")`.

## Install-time scan

Before `.dlm`, `.lm`, `.uplm` and `.restore` Uroboros reads the module source (`uroboros/scan.py`). It's a heuristic,
not a sandbox: it catches typical malicious code, not everything.

**Dangerous**: install stops until the user confirms explicitly (button or `-f`):

- session access: `client.session.save()`, `StringSession.save`, `auth_key`, `api_hash`, `.session` files,
  `uroboros.db`;
- account takeover requests: terminating sessions, deleting the account, changing 2FA or phone, QR login,
  `log_out`, spending stars, transferring gifts;
- hidden code: `exec`/`eval` of `base64`/`zlib`/`marshal`;
- Uroboros system settings: `self.loader.security`, `self.loader.ratelimit`, `uroboros.inline` and
  `uroboros.security` keys, `UROBOROS_API_HASH` and `UROBOROS_BOT_TOKEN`.

**Suspicious**: shown in the reply but doesn't block install: environment variables, shell commands
(`subprocess`, `os.system`), file deletion, `config.json`, `exec`/`eval` of a string, channel joins, `sys.modules`
changes.

GitHub modules are fetched by commit SHA; the confirmation and `.uplm` show which commit. `.uplm` shows each
module's diff and updates only after confirmation. Installed files are hash-protected: if a file changed outside
Uroboros and now has dangerous code, it won't load at startup.

At runtime third-party modules are restricted too: they can't read `self.client.session`, open the session,
`config.json` or `uroboros.db`, send account takeover requests (terminating sessions, changing password or phone, QR
login, logout, spending stars), or pass session files to shell commands. Attempts raise `PermissionError` and notify
Saved Messages. Restrictions are lifted if the user confirmed the dangerous code on install or ran
`.security trust <module>`.

If your module really needs any of this, explain why in its description: the user sees the warning and decides.
