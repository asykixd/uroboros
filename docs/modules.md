# Как писать модули

Модуль — это `.py`-файл с одним или несколькими классами-наследниками `Module`.
Встроенные модули Uroboros написаны на том же API, их код — хороший пример: [`uroboros/modules/`](../uroboros/modules).
Готовые примеры — в [`examples/`](../examples).

Установить свой модуль: отправьте файл в любой чат и ответьте на него `.lm`, либо `.dlm <ссылка>`.

## Минимальный модуль

```python
from uroboros import Module, command, utils


class Hello(Module):
    """Здоровается"""  # описание модуля для .help

    @command("hello", aliases=["hi"])
    async def hello(self, message):
        """[имя] — поздороваться"""  # описание команды для .help
        name = utils.get_args_raw(message) or "мир"
        await utils.answer(message, f"Привет, <b>{utils.escape_html(name)}</b>!")
```

Имя модуля — имя класса (или атрибут `name`). Все классы из одного файла устанавливаются,
обновляются и удаляются вместе.

## Шапка файла

Комментарии в начале файла читаются до запуска кода:

```python
# meta developer: @username
# meta version: 1.2
# requires_uroboros: 0.2
# requires: requests pillow
```

| Строка | Что делает |
|---|---|
| `# meta <ключ>: <значение>` | метаданные; `developer` и `version` показываются в `.help модуль` |
| `# requires_uroboros: 0.2` | минимальная версия ядра. На старой версии модуль не загрузится, а пользователь увидит, что нужно обновиться |
| `# requires: пакет ...` | pip-пакеты. Ставятся, только если при импорте чего-то не хватает, одна попытка |

## Жизненный цикл

| Метод | Когда вызывается |
|---|---|
| `async on_load()` | после загрузки: при старте, установке, обновлении, `.reload`. Если упадёт, модуль не загрузится |
| `async on_dlmod()` | один раз — при первой установке, после `on_load`. Не вызывается при рестарте и обновлении. Если упадёт, установка отменяется |
| `async on_unload()` | перед выгрузкой: удаление, обновление, `.reload`, остановка и рестарт бота. При остановке клиент уже может быть отключён |

До `on_load` загрузчик проставляет:

- `self.client` — `TelegramClient` (Telethon 1.x);
- `self.db` — хранилище модуля;
- `self.config` — настройки (если вы их объявили);
- `self.loader` — загрузчик (список модулей, команды);
- `self.inline` — формы с кнопками от inline-бота (см. [Inline-бот](#inline-бот)).

`__init__` вызывается без аргументов, и в нём этих атрибутов ещё нет. Объявляйте там только `self.config`.

При выгрузке ядро само останавливает фоновые задачи (`@loop`), снимает обработчики,
которые модуль повесил через `self.client.add_event_handler` или `@self.client.on(...)`,
и отключает кнопки форм модуля.

## Команды

```python
@command("name", aliases=["n"], doc="описание вместо докстринга")
async def name(self, message): ...
```

Без имени берётся имя метода (суффикс `cmd` отбрасывается: `pingcmd` → `ping`).
Команды срабатывают на ваших исходящих сообщениях и на сообщениях пользователей, которым
выданы права (см. [Доступ](#доступ)). Аргументы читаются через
`utils.get_args_raw(message)` (строка как есть) или `utils.get_args(message)` (список с учётом кавычек).

Если имя команды уже занято другим модулем, установка не пройдёт.

### Фильтры

```python
@command("ban", only_groups=True, only_reply=True)
```

| Фильтр | Команда работает |
|---|---|
| `only_pm=True` | только в личных сообщениях |
| `only_groups=True` | только в группах (и супергруппах) |
| `only_channels=True` | только в каналах |
| `chats=[id, ...]` | только в перечисленных чатах (id в формате Telethon) |
| `only_reply=True` / `no_reply=True` | только ответом на сообщение / только не ответом |
| `filter=lambda m: ...` | если функция вернула `True` |

`only_pm`, `only_groups` и `only_channels` взаимоисключающие. Если сообщение не подходит,
команда не вызывается, а пользователь получает ответ с причиной. Ограничения видны в `.help`.

### Доступ

```python
@command("note", access="support")
```

`access` — кто может выполнять команду, кроме этого аккаунта: `owner` (только владельцы),
`sudo` (по умолчанию: sudo и владельцы), `support` (support, sudo и владельцы) или `everyone`.
Пользователь добавляет людей в группы командами `.owner`, `.sudo`, `.support` и меняет уровень
любой команды через `.security <команда> <уровень>`. Команды, которые дают доступ к серверу или
аккаунту (`eval`, установка модулей), объявляйте с `access="owner"`.

Запросы к Telegram из стороннего модуля считаются. Если модуль отправил слишком много запросов
(по умолчанию больше 60 за 30 секунд), он замораживается на 5 минут: его запросы бросают
`ModuleFrozen` (наследник `LoadError`), а пользователь получает уведомление в «Избранное».
Настройка — `.security flood`.

Если команду вызвал другой пользователь, `message.out` равно `False`: `utils.answer` ответит на его
сообщение, а не будет редактировать. Кнопки формы, отправленной в ответ на его команду, доступны и ему.

### Ошибки

Необработанное исключение показывается пользователю с traceback. Если ошибка ожидаемая
(«нет такого пользователя»), бросьте `LoadError("текст")` из `uroboros.errors`: пользователь
увидит только текст. Длинный флуд-лимит Telegram (`FloodWaitError`) диспетчер показывает
сам: «повторите через …».

## Вотчеры

```python
from uroboros import watcher

@watcher(only_incoming=True, filter=lambda m: m.is_private)
async def watch(self, message): ...
```

Вызываются на каждое новое сообщение (входящее и исходящее), параллельно друг с другом.
Параметры: `only_outgoing`, `only_incoming`, `filter`. Исключения только пишутся в лог.

## Фоновые задачи

```python
from uroboros import loop

@loop(interval=60, autostart=True, wait_before=False)
async def refresh(self): ...
```

Метод вызывается каждые `interval` секунд. После загрузки `self.refresh` — объект управления:
`self.refresh.start(interval=None)`, `self.refresh.stop()`, `self.refresh.running`,
`await self.refresh()` — вызов вне расписания. Ошибка в одном вызове пишется в лог и не останавливает цикл.
`autostart=False` — не запускать сразу после `on_load`. `wait_before=True` — подождать интервал перед первым вызовом.

## Хранилище

```python
self.set("key", {"любое": ["json-значение"]})
self.get("key", default)
self.db.delete("key")
```

У каждого модуля своё хранилище (по имени модуля). Значения проходят через JSON:
`tuple` вернётся `list`, ключи словарей — строками. `get` отдаёт копию: чтобы сохранить
изменения, вызовите `set`. Хранилище попадает в `.backup`.

## Настройки

```python
from uroboros import ConfigValue, ModuleConfig, validators

def __init__(self):
    self.config = ModuleConfig(
        ConfigValue("limit", 10, "Сколько показывать", validators.Integer(minimum=1, maximum=100)),
        ConfigValue("mode", "fast", "Режим", validators.Choice(["fast", "slow"])),
    )

# в командах:
self.config["limit"]
```

Пользователь меняет их командой `.cfg модуль ключ значение` и сбрасывает через `.rcfg`.
Значение от пользователя приходит строкой, валидатор приводит его к нужному типу.

| Валидатор | Принимает |
|---|---|
| `String(min_len=None, max_len=None)` | строку |
| `Integer(minimum=None, maximum=None)` | целое число |
| `Float()` | число |
| `Boolean()` | да/нет, true/false, 1/0, on/off |
| `Choice([...])` | одно из значений |

Свой валидатор — любая функция `value -> value`, которая бросает `validators.ValidationError` с текстом для пользователя.

## Строки

```python
strings = {
    "done": "✅ Готово: <b>{name}</b>",
}

self.strings("done", name=user_input)  # подставленное экранируется как HTML
self.strings["done"]                    # шаблон как есть
```

Шаблон может содержать разметку, а подставляемые значения экранируются. Если значение —
уже готовый HTML, оберните его в `utils.Html(...)`.

## Библиотеки

Общий код для нескольких модулей выносится в библиотеку:

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
# в модуле
async def on_load(self):
    self.textlib = await self.import_lib("https://github.com/you/repo/blob/main/textlib.py")
```

- `import_lib` возвращает экземпляр класса `Library` из файла. Если такого класса нет, возвращается сам Python-модуль: подойдёт обычный файл с функциями.
- Библиотека загружается один раз на всех. Она выгружается, когда выгружен последний модуль, который её подключил.
- Исходник кешируется на диске, поэтому после рестарта сеть не нужна. `import_lib(url, reload=True)` скачивает библиотеку заново.
- У библиотеки есть `self.client`, `self.loader` и своё хранилище `self.db`.

## Inline-бот

Вместе с юзерботом работает бот на aiogram 3. При первом запуске Uroboros сам создаёт
его через @BotFather и включает inline-режим. Свой бот: `.inlinebot <токен>` или переменная
`UROBOROS_BOT_TOKEN`. Через этого бота модули показывают сообщения с кнопками.

```python
@command("counter")
async def counter(self, message):
    """— счётчик с кнопками"""
    await self.inline.form(message, "Счёт: 0", self._buttons(0))

def _buttons(self, value):
    return [
        [{"text": "−", "callback": self._add, "args": (value, -1)},
         {"text": "+", "callback": self._add, "args": (value, 1)}],
        [{"text": "✍️ Задать", "input": "Новое значение", "handler": self._typed}],
        [{"text": "Сбросить", "callback": self._add, "args": (0, 0), "confirm": "Сбросить счёт?"},
         {"text": "✖ Закрыть", "action": "close"}],
    ]

async def _add(self, call, value, delta):
    value += delta
    await call.edit(f"Счёт: {value}", self._buttons(value))

async def _typed(self, call, text):
    if not text.lstrip("-").isdigit():
        await call.edit("❌ Нужно целое число")
        return
    await call.edit(f"Счёт: {text}", self._buttons(int(text)))
```

`self.inline.form(message, text, buttons=None, *, photo=None, always_allow=())` отправляет форму
вместо своего сообщения с командой и возвращает `InlineMessage` с методами `edit(text, buttons)`,
`delete()` и `unload()`. `photo` — ссылка на картинку, тогда `text` становится подписью.

Кнопка — словарь с `text` и одним действием:

| Ключ | Что делает кнопка |
|---|---|
| `"callback": self.method` | вызывает `method(call, *args, **kwargs)`, аргументы — в `"args"` и `"kwargs"` |
| `"confirm": "Точно?"` | вместе с `callback`: сначала спрашивает «Да / Отмена» |
| `"url": "https://..."` | открывает ссылку |
| `"input": "подсказка", "handler": self.method` | ввод текста: подставляет в поле ввода `@бот <id> `, пользователь дописывает значение и выбирает вариант. Вызывается `method(call, text, *args)` |
| `"data": "строка"` | обычная callback-кнопка для `@callback_handler` (до 64 байт) |
| `"action": "close"` | удаляет форму |

`buttons` — список рядов, один ряд (список словарей) или одна кнопка.

`call` (`InlineCall`) — нажатие: `await call.edit(text, buttons)` меняет форму (`buttons=None`
убирает кнопки, без аргумента — оставляет прежние), `await call.answer("текст", show_alert=False)`
показывает подсказку, `call.delete()` удаляет форму, `call.from_user` — кто нажал,
`call.query` — исходный `CallbackQuery` aiogram. Если колбэк бросит `LoadError`, пользователь увидит
её текст во всплывающем окне.

Ещё два вида форм:

- `await self.inline.list(message, pages)` — страницы текста, листаются кнопками ◀ ▶;
- `await self.inline.gallery(message, photos, caption="")` — картинки по ссылкам. `photos` — список
  ссылок (◀ ▶) или async-функция, которая возвращает новую ссылку (кнопка «Ещё»).

Кнопки нажимает только владелец аккаунта; другим пользователям можно разрешить через
`always_allow=[id, ...]`. Формы живут в памяти: после рестарта старые кнопки отвечают «Кнопка устарела».

Если бот не запущен (нет токена, выключен через `.inlinebot off`), `form` бросает `InlineError`
из `uroboros.errors` — пользователь увидит причину. Проверить заранее: `self.inline.available`.
Так же `InlineError` приходит, если в чате запрещены inline-боты: встроенные команды в этом случае
отвечают обычным текстом. Для всего остального есть `self.inline.bot` — экземпляр `aiogram.Bot`.

### Inline-команды и колбэки

```python
from uroboros import callback_handler, inline_handler

@inline_handler()
async def echo_inline_handler(self, query):
    """<текст> — повторить"""
    return {"title": "Эхо", "description": query.args, "message": utils.escape_html(query.args or "…")}

@callback_handler("vote:")
async def vote(self, call):
    await call.answer(f"Голос: {call.data.removeprefix('vote:')}")
```

- `@inline_handler(name=None)` отвечает на `@бот <name> аргументы` (без имени — имя метода без
  `_inline_handler`). `query.args` — текст после имени. Вернуть можно словарь или список словарей
  с ключами `title`, `description`, `message` (HTML), `buttons`, `photo`. Пустой запрос `@бот`
  показывает список inline-команд.
- `@callback_handler(prefix=None)` получает нажатия кнопок с `"data"`, которые начинаются с `prefix`.

## utils

| Функция | Что делает |
|---|---|
| `await answer(message, text)` | ответ на команду (HTML): редактирует своё сообщение, длинный текст отправляет файлом |
| `await answer_file(message, file, caption=None)` | отправляет файл (ответом на то же сообщение, что и команда) и удаляет сообщение с командой |
| `get_args_raw(message)` / `get_args(message)` | аргументы команды строкой / списком |
| `await get_reply(message)` | сообщение, на которое ответили командой, или `None` |
| `await get_user(message)` | отправитель сообщения |
| `await get_target(message, arg=None)` | о ком команда: автор сообщения в ответе → `@username`/id из аргумента → собеседник в личке → `None` |
| `get_chat_id(message)` | id чата (формат Telethon) |
| `await run_sync(func, *args, **kwargs)` | блокирующую функцию — в поток, чтобы бот не зависал |
| `escape_html(text)` | экранирование для HTML-разметки |
| `quote(text, expandable=False)` | цитата Telegram, `expandable` — свёрнутая |
| `Html(text)` | пометка «это уже HTML» для `escape_html` и `strings` |
| `get_prefix(db)` | текущий префикс команд (`get_prefix(self.db.raw)`) |
| `format_duration(seconds)` | `3 д 04:05:06` |

## Оформление ответов

Встроенные модули пишут в одном стиле. Свои модули лучше оформлять так же:

- в начале сообщения ровно один эмодзи-статус: ✅ успех, ❌ ошибка, ⏳ процесс;
- без значков в каждой строке;
- списки и подробности — в `utils.quote(...)`, длинное — в `utils.quote(..., expandable=True)`;
- код — в `<pre>`;
- пользовательский текст всегда пропускайте через `utils.escape_html`.

## Проверка при установке

Перед `.dlm`, `.lm`, `.uplm` и `.restore` Uroboros читает исходник модуля (`uroboros/scan.py`). Это эвристика,
а не песочница: она ловит типичный вредный код, но не любой.

**Опасное** — установка останавливается, пока пользователь явно не подтвердит (кнопкой или флагом `-f`):

- доступ к сессии: `client.session.save()`, `StringSession.save`, `auth_key`, `api_hash`, файлы `.session`, `uroboros.db`;
- запросы, которыми угоняют аккаунт: завершение сеансов, удаление аккаунта, смена пароля 2FA или номера, вход по QR,
  `log_out`, траты звёзд и передача подарков;
- скрытый код: `exec`/`eval` от `base64`/`zlib`/`marshal`;
- системные настройки Uroboros: `self.loader.security`, `self.loader.ratelimit`, ключи `uroboros.inline` и
  `uroboros.security`, переменные `UROBOROS_API_HASH` и `UROBOROS_BOT_TOKEN`.

**Подозрительное** — показывается в ответе, но не мешает установке: переменные окружения, запуск команд
(`subprocess`, `os.system`), удаление файлов, `config.json`, `exec`/`eval` от строки, подписка на каналы,
изменения `sys.modules`.

Модули с GitHub скачиваются по ссылке на конкретный коммит: в подтверждении и в `.uplm` видно, какой коммит
ставится. `.uplm` сначала показывает, что изменилось в каждом модуле, и обновляет только после подтверждения. Файлы
установленных модулей защищены хешем: если файл изменили не через Uroboros и в нём появился опасный код, при
запуске модуль не загрузится.

Если модулю действительно нужно что-то из этого, объясните зачем в описании модуля: пользователь увидит
предупреждение и решит сам.
