# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Проект

Uroboros — модульный юзербот для Telegram (Python ≥3.10 + Telethon 1.x), аналог Hikka, написанный с нуля. Лицензия AGPL-3.0: код Hikka (тоже AGPL) можно переносить. Интерфейс и сообщения бота — только на русском. Основная ветка — `master`.

## Команды

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'   # установка для разработки
.venv/bin/python -m uroboros                                 # запуск (интерактивный логин в консоли)
.venv/bin/python -m pytest                                   # все тесты
.venv/bin/python -m pytest tests/test_core.py::test_install_and_uninstall   # один тест
```

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check .   # линтер и форматтер (то же проверяет CI)
```

Тесты не ходят в сеть и не требуют Telegram: `Loader` создаётся с `client=None` и `Database(":memory:")`, корутины гоняются через `asyncio.run` (pytest-asyncio не используется).

`api_id`/`api_hash` можно передать через `UROBOROS_API_ID`/`UROBOROS_API_HASH`, они приоритетнее `config.json`. Данные рантайма лежат в `./data` (путь меняется через `UROBOROS_DATA`): `config.json` (api_id/api_hash), сессия `uroboros.session`, `uroboros.db`, `modules/`, `uroboros.log`, `uroboros.lock` (блокировка от второго экземпляра). Это доступ к аккаунту: не коммитить и не читать без нужды.

## Архитектура

Поток запуска в `main.py`: `load_config` → `Database` → `TelegramClient.start` → `InlineManager.start` → `Loader.load_all` → `Dispatcher.install` → `run_until_disconnected`. Рестарт: `utils.restart()` выставляет флаг и отключает клиент, а `main()` после выхода из цикла выгружает модули и делает `os.execv`. На Windows `main()` сначала запускает надзирателя (`supervise`), который держит бота дочерним процессом и перезапускает его, когда тот выходит с кодом `RESTART_EXIT_CODE` (75).

**Загрузчик (`loader.py`).** Модули загружаются не импортом, а через `exec` исходника в `ModuleType`:
- Встроенные модули из `uroboros/modules/*.py` читаются как текст и получают имя `uroboros.modules.<stem>`.
- Сторонние получают `uroboros.ext.<stem>_<n>`. Их исходник сохраняется в `data/modules/<stem>.py`, а источник — в БД (`uroboros.loader` / `installed`: stem → url).
- Единица выгрузки — файл (stem): все классы-наследники `Module` из одного файла выгружаются вместе.
- В `_load` порядок важен: сначала проверяются конфликты (нельзя заменить встроенный модуль, нельзя занять чужую команду), потом выгружаются заменяемые stem'ы, затем регистрация и `on_load`. Если `on_load` падает, весь stem откатывается.
- `# requires:` → `pip install` только при `ImportError`, одна попытка.
- Шапка файла читается до `exec`: `# meta ключ: значение` → `inst._meta`, `# requires_uroboros: X` — проверка версии ядра.
- `LoadError` (`errors.py`, реэкспорт из `loader`) — ошибка, текст которой показывается пользователю. Диспетчер выводит её без traceback. Скачивание — `download.py`.

**Диспетчер (`dispatcher.py`).** Один обработчик `NewMessage`. Команды срабатывают только на исходящих сообщениях. Цепочка разрешения: префикс → пользовательские алиасы (БД, `uroboros.main`/`aliases`) → `Loader.get_command`, которая учитывает и алиасы из `@command(aliases=...)`. Вотчеры получают все сообщения параллельно, их исключения только логируются.

**API модулей** (публичный — то, что экспортирует `uroboros/__init__.py`):
- `Module` с `on_load`/`on_unload`.
- Декораторы `@command`, `@watcher`.
- `ModuleConfig`/`ConfigValue` и `validators` — валидаторы принимают и строки, потому что `.cfg` передаёт значение текстом.
- `@loop`, `Library`.
- `@inline_handler`, `@callback_handler`, `self.inline.form` / `list` / `gallery` (`InlineCall`, `InlineError`).
- `utils`: `answer`, `answer_file`, `get_args_raw`, `get_args`, `get_reply`, `get_user`, `get_target`, `get_chat_id`, `run_sync`, `quote`, `escape_html`, `Html`, `get_prefix`.

Загрузчик проставляет модулю `client`, `loader`, `inline`, `db` (`ModuleDB`, owner = имя модуля), оборачивает `strings` в `Strings` (вызов `self.strings("key", **kw)` экранирует подстановки) и привязывает `config` к БД (ключ `__config__`). При выгрузке stem'а загрузчик останавливает `@loop`-задачи (`loops.py`), снимает обработчики Telethon, чьи функции объявлены в файле модуля, и выгружает библиотеки (`Library`, `self.import_lib`), у которых не осталось модулей-пользователей. Исходники библиотек кешируются в `data/modules/libs/`, ссылки — в БД (`uroboros.loader`/`libs`). `on_dlmod` вызывается в `Loader.install` только если stem ещё не был установлен.

Документация для авторов модулей — `docs/modules.md`. Примеры из `examples/` загружаются в `tests/test_examples.py`: при изменении API их нужно обновлять. Пример с `# requires_uroboros: X` не загрузится, если `__version__` меньше X, поэтому версия на master должна быть не меньше той, что требуют примеры. API намеренно повторяет Hikka (`utils.answer`, `strings`, `config`), чтобы будущий адаптер совместимости был тонким.

**Inline-бот (`inline/`).** aiogram 3 в том же процессе, `InlineManager` (`loader.inline`). Ошибка запуска бота не роняет юзербот: причина в `manager.error`, её показывает `.inlinebot`. Токен: `UROBOROS_BOT_TOKEN` → БД (`uroboros.inline`/`token`) → создание через @BotFather (`botfather.py`, там же включаются inline-режим и inline feedback). Форма: юзербот делает inline-запрос к своему боту с id формы и отправляет результат (`click`). `inline_message_id` бот узнаёт из `chosen_inline_result` или из первого нажатия. Кнопки ввода подставляют `@бот <id> `, текст приходит в `chosen_inline_result`, служебное сообщение `INPUT_MARKER` юзербот удаляет. Формы (`Unit`) живут в памяти и снимаются при выгрузке stem'а. Отвечает бот только владельцу и `always_allow`. Модули получают прокси `self.inline` (`inline.Inline`). Тесты подменяют бота и клиента заглушками из `tests/fake_inline.py`.

**БД (`database.py`).** Синхронный key-value на `sqlite3` с кешем в памяти (как синхронные `db.get`/`db.set` в Hikka). `get` отдаёт deepcopy, значения проходят через JSON (tuple становится list). Системные владельцы ключей: `uroboros.main` (prefix, aliases), `uroboros.loader` (installed), `uroboros.inline` (token, configured, disabled).

**GitHub (`github.py`).** Преобразует blob-ссылки и короткие пути `owner/repo/path` в адреса `raw.githubusercontent.com/.../HEAD/...`, а списки модулей репозитория получает через GitHub contents API. В `.dlm` разбор идёт по порядку: `owner/repo` → показать список модулей; ссылка или путь → скачать; просто имя → искать в подключённых репозиториях (БД модуля Loader, ключ `repos`).

## Стиль сообщений бота

Все ответы — HTML через `utils.answer`: свой исходящий текст он редактирует, если текст длиннее 4096 символов — отправляет файлом. Стиль сдержанный:
- в начале сообщения ровно один эмодзи-статус: ✅ успех, ❌ ошибка, ⏳ процесс, 📦 модули, ⚙️ настройки, 🔗 алиасы и репозитории, 🗑 удаление;
- без декоративных значков в каждой строке;
- списки и подробности — в цитатах `utils.quote(...)`, длинное и traceback — в `utils.quote(..., expandable=True)`;
- код — в `<pre>`.

## Планы и ограничения

План по версиям — в `ROADMAP.md` (сделанное отмечено `[x]`). Принципы оттуда, которые влияют на код:
- ядро маленькое: встроенные модули (`uroboros/modules/`) пишутся только на публичном API, как сторонние;
- только обычный Telethon 1.x — без форков и без перехода на Telethon 2 до его стабильного релиза;
- новая зависимость должна ставиться в Termux без компиляции (исключение — aiogram 3: `pydantic-core` там собирается через Rust, так решил пользователь);
- до 1.0 каждый релиз — с dev-флагом: версия `X.Y.Z-dev` (в `pyproject.toml` и `uroboros/__init__.py`, pip нормализует её в `X.Y.Z.dev0`), тег `vX.Y.Z-dev`, на GitHub — pre-release. Без `-dev` выходит только 1.0 и дальше. Старые теги `v0.1.0b1`, `v0.1.0b2`, `v0.1.1b2` выпущены до этого правила.
- сейчас релизы не делаются: только коммиты и push в `master`, без тегов и GitHub-релизов, пока пользователь не попросит. Когда попросит — релиз в конце этапа, а не после каждого коммита: зелёный CI → коммит с версией → аннотированный тег → `gh release create --prerelease` с заметками на русском. Номер версии подтверждать у пользователя.

Ещё не сделано: доступ и безопасность (0.4), веб-панель первого входа, адаптер Hikka. Модули Hikka без адаптера не загрузятся.
