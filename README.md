# Uroboros

Модульный юзербот для Telegram на Python + Telethon.

> Статус: **бета** (`0.1.0b1`) — готово ядро: загрузчик модулей, команды, настройки, установка модулей с GitHub.
> Дальше: inline-бот, вход через веб-панель, совместимость с модулями Hikka.

> ⚠️ Юзербот работает от имени вашего аккаунта. Спам, массовые рассылки и флуд
> запросами могут привести к бану. Сначала проверяйте на втором аккаунте.
> Сторонние модули получают полный доступ к аккаунту и серверу — ставьте только те, которым доверяете.

## Установка

```bash
git clone https://github.com/asykixd/uroboros && cd uroboros
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/python -m uroboros
```

При первом запуске Uroboros спросит `api_id` и `api_hash` (их можно получить на https://my.telegram.org/apps),
затем номер телефона, код и пароль 2FA. Данные и сессия хранятся в `./data`
(путь меняется переменной `UROBOROS_DATA`). `api_id`/`api_hash` можно передать через
`UROBOROS_API_ID` / `UROBOROS_API_HASH`.

## Команды

| Команда | Что делает |
|---|---|
| `.help [модуль]` | список модулей / справка |
| `.dlm <ссылка>` | установить модуль по ссылке (GitHub `blob`-ссылки понимаются) |
| `.dlm owner/repo/модуль` | установить модуль из репозитория на GitHub |
| `.dlm owner/repo` | показать модули в репозитории |
| `.dlm <модуль>` | найти модуль в подключённых репозиториях |
| `.addrepo`, `.delrepo`, `.repos` | подключённые репозитории модулей |
| `.lm` | установить модуль из файла (ответом на файл) |
| `.ulm <модуль>` | удалить модуль |
| `.reload` | перезагрузить модули |
| `.cfg [модуль] [ключ] [значение]` | настройки модулей, `.rcfg` — сброс |
| `.setprefix`, `.alias`, `.unalias`, `.aliases` | префикс и алиасы |
| `.e <код>`, `.t <команда>` | Python eval и shell |
| `.ping`, `.info`, `.restart`, `.update` | система |

## Пишем модуль

```python
# requires: requests
from uroboros import ConfigValue, Module, ModuleConfig, command, utils, validators, watcher


class Hello(Module):
    """Пример модуля"""

    def __init__(self):
        self.config = ModuleConfig(
            ConfigValue("times", 1, "Сколько раз здороваться", validators.Integer(minimum=1, maximum=5)),
        )

    async def on_load(self):
        self.db.set("loaded", True)  # у каждого модуля своё хранилище

    @command("hello", aliases=["hi"])
    async def hello(self, message):
        """[имя] — поздороваться"""
        name = utils.get_args_raw(message) or "мир"
        await utils.answer(message, f"Привет, <b>{utils.escape_html(name)}</b>! " * self.config["times"])

    @watcher(only_incoming=True)
    async def watch(self, message):
        ...  # вызывается на каждое входящее сообщение
```

Внутри модуля доступны `self.client` (TelegramClient), `self.db` (`get`/`set`/`delete`),
`self.config` и `self.loader`. Для оформления есть `utils.quote(text, expandable=True)` — цитата Telegram (свёрнутая при `expandable`). Строка `# requires:` перечисляет pip-пакеты:
они ставятся автоматически, если при импорте модуля чего-то не хватает.

## Тесты

```bash
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest
```

## Лицензия

AGPL-3.0, см. [LICENSE](LICENSE).
