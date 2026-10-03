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
- `self.loader` — загрузчик (список модулей, команды).

`__init__` вызывается без аргументов, и в нём этих атрибутов ещё нет. Объявляйте там только `self.config`.

При выгрузке ядро само останавливает фоновые задачи (`@loop`) и снимает обработчики,
которые модуль повесил через `self.client.add_event_handler` или `@self.client.on(...)`.

## Команды

```python
@command("name", aliases=["n"], doc="описание вместо докстринга")
async def name(self, message): ...
```

Без имени берётся имя метода (суффикс `cmd` отбрасывается: `pingcmd` → `ping`).
Команды срабатывают только на ваших исходящих сообщениях. Аргументы читаются через
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
