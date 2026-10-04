---
hide:
  - navigation
  - toc
---

<div class="uro-hero" markdown>

![Uroboros](assets/logo.svg)

# Uroboros

Модульный юзербот для Telegram на Python и Telethon. Команды и сообщения на русском, модули ставятся одной
командой, а аккаунт защищён от вредного кода.

[🚀 Установить](install.md){ .md-button .md-button--primary }
[🧩 Писать модули](modules.md){ .md-button }

</div>

<div class="grid cards" markdown>

-   📦 **Модули одной командой**

    ---

    `.dlm погода` — и модуль из официального репозитория установлен. Свои репозитории подключаются через
    `.addrepo`, поиск — `.search`.

-   🛡 **Защита аккаунта**

    ---

    Код модуля проверяется до установки, а во время работы модули не видят сессию и не могут угнать аккаунт.
    [Подробнее](security.md)

-   🤖 **Кнопки и формы**

    ---

    Встроенный inline-бот: настройки, справка и подтверждения — кнопками прямо в чате.

-   🔁 **Модули Hikka и FTG**

    ---

    Модули Hikka и FTG загружаются без правок через встроенный адаптер. [Что поддерживается](hikka.md)

-   🌿 **Стабильная и dev-ветки**

    ---

    `master` — проверенное, `dev` — новое. Переключение одной командой `.dev on` / `.dev off`, откат при ошибке.

-   🐧 **Работает везде**

    ---

    Linux и VPS, Termux на Android, Docker, Windows и macOS. Вход через веб-панель или по QR-коду.

</div>

## Как это выглядит

<div class="tg-chat" markdown>
<div class="tg-msg">
🐍 <b>Uroboros</b>
<blockquote>👤 Аккаунт: <b>Evelin</b><br>⏱ Аптайм: <code>3 д 04:05:06</code><br>📦 Модулей: <code>13</code> · команд: <code>35</code><br>⌨️ Префикс: <code>.</code><br>🌿 Ветка: <code>master</code></blockquote>
💡 <i><code>.help</code> — все команды</i>
<span class="tg-time">12:00 ✓✓</span>
</div>
<div class="tg-msg">
✅ <b>Модуль Notes загружен</b>
<blockquote>💾 <code>.save</code> — сохранить заметку<br>📖 <code>.note</code> — показать заметку<br>🗂 <code>.notes</code> — список заметок</blockquote>
<span class="tg-time">12:01 ✓✓</span>
</div>
</div>

## Быстрый старт

=== "Linux и macOS"

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

Бот откроет веб-панель входа: введите `api_id` и `api_hash` с [my.telegram.org](https://my.telegram.org),
номер и код — или войдите по QR-коду. Потом напишите в любом чате `.help`.

## Документация

- 🚀 [Установка](install.md) — все системы, служба systemd, обновления, ветки
- ⌨️ [Команды](commands.md) — все встроенные команды и уровни доступа
- 🛡 [Безопасность](security.md) — доступ к командам, проверка модулей, защита во время работы
- 🧩 [Как писать модули](modules.md) и [примеры](examples.md)
- 🔁 [Модули Hikka и FTG](hikka.md)
- 📐 [Стабильность API](stability.md)
- 🗺 [План развития](https://github.com/asykixd/uroboros/blob/master/ROADMAP.md)
