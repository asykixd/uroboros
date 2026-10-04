---
hide:
  - navigation
  - toc
---

<div class="uro-hero" markdown>

![Uroboros](assets/logo.svg)

# Uroboros

Modular Telegram userbot on Python and Telethon. Modules install with one command, and your account is protected
from malicious code.

[🚀 Install](install.md){ .md-button .md-button--primary }
[🧩 Write modules](modules.md){ .md-button }

</div>

<div class="grid cards" markdown>

-   📦 **One-command modules**

    ---

    `.dlm weather` installs a module from the official repo. Add your own repos with `.addrepo`, search with
    `.search`.

-   🛡 **Account protection**

    ---

    Module code is scanned before install; at runtime modules can't read the session or hijack the account.
    [More](security.md)

-   🤖 **Buttons and forms**

    ---

    Built-in inline bot: settings, help and confirmations as buttons right in the chat.

-   🔁 **Hikka and FTG modules**

    ---

    Hikka and FTG modules load unchanged through the built-in adapter. [What's supported](hikka.md)

-   🌿 **Stable and dev channels**

    ---

    `master` is tested, `dev` is new. Switch with `.dev on` / `.dev off`, rollback on failure.

-   🐧 **Runs anywhere**

    ---

    Linux and VPS, Termux on Android, Docker, Windows and macOS. Log in via web panel or QR code.

</div>

## What it looks like

<div class="tg-chat" markdown>
<div class="tg-msg">
🐍 <b>Uroboros</b>
<blockquote>👤 Account: <b>Evelin</b><br>⏱ Uptime: <code>3d 04:05:06</code><br>📦 Modules: <code>13</code> · commands: <code>35</code><br>⌨️ Prefix: <code>.</code><br>🌿 Branch: <code>master</code></blockquote>
💡 <i><code>.help</code> — all commands</i>
<span class="tg-time">12:00 ✓✓</span>
</div>
<div class="tg-msg">
✅ <b>Notes module loaded</b>
<blockquote>💾 <code>.save</code> — save a note<br>📖 <code>.note</code> — show a note<br>🗂 <code>.notes</code> — list notes</blockquote>
<span class="tg-time">12:01 ✓✓</span>
</div>
</div>

## Quick start

=== "Linux and macOS"

    ```bash
    curl -fsSL https://raw.githubusercontent.com/asykixd/uroboros/master/install.sh | sh
    ```

=== "Termux"

    ```bash
    pkg install -y curl && curl -fsSL https://raw.githubusercontent.com/asykixd/uroboros/master/install.sh | sh
    ```

=== "Docker"

    ```bash
    git clone https://github.com/asykixd/uroboros && cd uroboros && docker compose up -d
    ```

=== "pip"

    ```bash
    python3 -m venv uroboros && uroboros/bin/pip install uroboros-userbot && cd uroboros && bin/uroboros
    ```

The bot opens a web login panel: enter `api_id` and `api_hash` from [my.telegram.org](https://my.telegram.org),
phone and code, or log in by QR code. Then type `.help` in any chat. The bot speaks Russian for now; English is next.

## Docs

- 🚀 [Install](install.md): all platforms, systemd, updates, branches
- ⌨️ [Commands](commands.md): built-in commands and access levels
- 🛡 [Security](security.md): command access, module scanning, runtime protection
- 🧩 [Writing modules](modules.md) and [examples](examples.md)
- 🔁 [Hikka and FTG modules](hikka.md)
- 📐 [API stability](stability.md)
- 🗺 [Roadmap](https://github.com/asykixd/uroboros/blob/master/ROADMAP.md)
