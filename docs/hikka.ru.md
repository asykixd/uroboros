# Модули Hikka и FTG

Uroboros загружает модули Hikka и FTG без правок: `.dlm` и `.lm` сами узнают такой модуль
(`from .. import loader, utils`, `loader.Module`, `@loader.tds`, `hikkatl`) и загружают его через адаптер.

## Как это работает

Модуль Hikka исполняется как подмодуль пакета `uroboros.hikka.modules`, поэтому его
`from .. import loader, utils` получает шимы Uroboros:

- `loader` — `Module`, `Library`, декораторы `command`, `watcher`, `inline_handler`, `callback_handler`,
  `loop`, `tag`, `raw_handler`, права `owner`, `sudo`, `support`, `unrestricted`, `ModuleConfig`,
  `ConfigValue`, `validators`, `StopLoop`, `SelfUnload`;
- `utils` — `answer`, `answer_file`, `get_args*`, `get_chat_id`, `get_target`, `get_user`, `escape_html`,
  `run_sync`, `get_link`, `chunks`, `rand`, `smart_split`, `remove_html`, `mime_type`, служебные чаты модулей
  `asset_channel`, `dnd`, `invite_inline_bot`, `set_avatar` и другие;
- `validators` — все валидаторы Hikka с подсказками на русском;
- `inline.types` — `InlineCall`, `InlineQuery`, `InlineMessage`;
- `database` (`Database` для аннотаций), `version`, `main`, `security`, `types` — то немногое, на что ссылаются модули.

`import hikkatl...` (форк Telethon из Hikka) и `herokutl` (из Heroku) отдают обычный Telethon.
Модули с `# scope: hikka_only` загружаются: эта пометка значит «нужен Hikka, а не FTG».

Что переводится из Hikka:

| В Hikka | В Uroboros |
|---|---|
| `xxxcmd` и `@loader.command(ru_doc=..., alias=...)` | команда с описанием на русском и алиасами |
| `@loader.watcher(only_pm=True, no_commands=True, ...)` | вотчер с фильтром по тегам Hikka |
| `@loader.loop(interval, autostart)` | `@loop`, `self.<метод>.start()/stop()/status` |
| `client_ready(client, db)`, `on_dlmod(client, db)` | вызываются после загрузки и при первой установке |
| `strings` + `strings_ru` | строки на русском, `self.strings("ключ")` |
| `self.get` / `self.set`, `self.db.get(владелец, ключ)` | то же хранилище, данные модуля — под именем класса, как в Hikka |
| `self.inline.form(text, message, reply_markup=...)`, `list`, `gallery` | формы inline-бота Uroboros |
| `@loader.owner`, `@loader.sudo`, `@loader.support`, `@loader.unrestricted` | уровни доступа `.security` |

Команды модулей Hikka по умолчанию доступны только владельцам — как в Hikka.

## Что не поддерживается

При загрузке такой модуль получает понятную ошибку, а не падает посреди работы:

- внутренности Hikka: `from ..tl_cache`, `from .._internal`, `from .. import translations` и любые подмодули, кроме перечисленных выше;
- `import hikka` и Pyrogram-клиент Hikka (`hikkapyro`, `pyrogram`);
- модули с `# scope: hikka_min` новее 1.6.3.

Работают с ограничениями:

- групповые права Hikka (`@loader.group_admin`, `@loader.group_member`, `@loader.pm`) — команда доступна только владельцам;
- `self.request_join` — Uroboros не вступает в каналы по просьбе модуля, метод возвращает `False`;
- `db.pointer` и `self.pointer` возвращают обычные значения, а не «живые» списки и словари: изменения сохраняйте через `set`;
- `self.invoke`, `utils.asset_forum_topic` (есть только в форке Heroku) — ошибка при вызове;
- возможности Hikka-TL сверх обычного Telethon (например `client.hikka_me`) недоступны.

## Таблица совместимости

[hikka-compat.md](hikka-compat.md) собирает `scripts/hikka_compat.py`: он скачивает модули из популярных
репозиториев и пробует их загрузить. Скрипт исполняет чужой код, поэтому запускайте его в изоляции —
например вручную через GitHub Actions (workflow «Совместимость с Hikka»), таблица придёт артефактом.
