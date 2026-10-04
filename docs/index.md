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

The bot interface is in Russian for now; English is coming.

<div class="tg-chat" markdown>
<div class="tg-msg">
🐍 <b>Uroboros</b> <code>1.0.0</code>
<blockquote>👤 Аккаунт: <b>Алиса</b><br>⏱ Аптайм: <code>3 д 04:05:06</code><br>📦 Модулей: <code>13</code> · команд: <code>35</code><br>⌨️ Префикс: <code>.</code><br>🌿 Ветка: <code>master</code></blockquote>
💡 <i><code>.help</code> — все команды</i>
<span class="tg-time">12:00 ✓✓</span>
</div>
<div class="tg-msg">
✅ <b>Модуль Notes загружен</b>
<blockquote>💾 <code>.save</code> — сохранить заметку<br>📖 <code>.note</code> — показать заметку<br>🗂 <code>.notes</code> — список заметок</blockquote>
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
phone and code, or log in by QR code. Then type `.help` in any chat.

## Docs

- 🚀 [Install](install.md): all platforms, systemd, updates, branches
- ⌨️ [Commands](commands.md): built-in commands and access levels
- 🛡 [Security](security.md): command access, module scanning, runtime protection
- 🧩 [Writing modules](modules.md) and [examples](examples.md)
- 🔁 [Hikka and FTG modules](hikka.md)
- 📐 [API stability](stability.md)
- 🗺 [Roadmap](https://github.com/asykixd/uroboros/blob/master/ROADMAP.md)
