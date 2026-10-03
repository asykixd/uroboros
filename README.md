# Uroboros

Модульный юзербот для Telegram на Python + Telethon.

> Статус: **в разработке** (`0.3.0-dev`): до 1.0 API может меняться. Готово ядро (загрузчик модулей, команды,
> настройки, установка с GitHub, бэкап, логи), расширенный API модулей (фоновые задачи, фильтры команд, библиотеки)
> и inline-бот с формами и кнопками, доступ и защита от флуда, веб-панель первого входа и адаптер модулей Hikka/FTG.

> ⚠️ Юзербот работает от имени вашего аккаунта. Спам, массовые рассылки и флуд
> запросами могут привести к бану. Сначала проверяйте на втором аккаунте.
> Сторонние модули получают полный доступ к аккаунту и серверу — ставьте только те, которым доверяете.

## Установка

Linux, VPS, Termux и macOS:

```bash
curl -fsSL https://raw.githubusercontent.com/asykixd/uroboros/master/install.sh | sh
```

При первом запуске Uroboros пишет в консоль ссылку на веб-панель входа: откройте её в браузере, введите
`api_id` и `api_hash` (их можно получить на https://my.telegram.org/apps), номер телефона, код и пароль 2FA —
или отсканируйте QR-код в Telegram на телефоне. После входа панель выключается. Вход в консоли — `--cli`.

Вместе с юзерботом запускается inline-бот для форм с кнопками: при первом запуске Uroboros создаёт его сам
через @BotFather.

Docker, служба systemd, автозапуск в Termux, Windows и подробности — в [docs/install.md](docs/install.md).

## Команды

| Команда | Что делает |
|---|---|
| `.help [модуль]` | список модулей / справка |
| `.dlm [-f] <ссылка>` | установить модуль по ссылке (GitHub `blob`-ссылки понимаются); не из подключённого репозитория — с подтверждением, `-f` — без |
| `.dlm owner/repo/модуль` | установить модуль из репозитория на GitHub |
| `.dlm owner/repo` | показать модули в репозитории |
| `.dlm <модуль>` | найти модуль в подключённых репозиториях |
| `.addrepo`, `.delrepo`, `.repos` | подключённые репозитории модулей |
| `.lm` | установить модуль из файла (ответом на файл) |
| `.ulm <модуль>` | удалить модуль |
| `.uplm [модуль]` | обновить сторонние модули из источника |
| `.reload` | перезагрузить модули |
| `.cfg [модуль] [ключ] [значение]` | настройки модулей (с inline-ботом — кнопками), `.rcfg` — сброс |
| `.setprefix`, `.alias`, `.unalias`, `.aliases` | префикс и алиасы |
| `.e <код>`, `.t <команда>` | Python eval и shell |
| `.ping`, `.info`, `.restart`, `.update` | система |
| `.inlinebot [токен \| new \| on \| off]` | inline-бот: состояние, свой токен, новый бот |
| `.owner`, `.sudo`, `.support [add\|del пользователь]` | группы доступа: кому можно вызывать команды |
| `.security [команда уровень]` | права команд: `owner`, `sudo`, `support`, `everyone` |
| `.security flood [запросов секунд заморозка \| on \| off]` | защита от флуда: заморозка модулей, которые шлют слишком много запросов |
| `.logs [уровень]` | логи файлом в «Избранное» |
| `.backup`, `.restore` | бэкап БД и модулей в «Избранное» (без сессии) и восстановление ответом на архив |

Модули Hikka и FTG ставятся так же, через `.dlm` и `.lm`: адаптер загружает их без правок.
Что поддерживается — в [docs/hikka.md](docs/hikka.md).

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
        # вызывается на каждое входящее сообщение
        pass
```

Внутри модуля доступны `self.client` (TelegramClient), `self.get`/`self.set` (своё хранилище),
`self.config`, `self.strings` и `self.loader`. Ещё есть фильтры команд, фоновые задачи `@loop`,
библиотеки `self.import_lib(url)`, формы с кнопками `self.inline.form(...)` и хелперы в `utils`. Подробно — в [docs/modules.md](docs/modules.md),
примеры — в [examples/](examples).

## Тесты

```bash
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest
```

## Лицензия

AGPL-3.0, см. [LICENSE](LICENSE).
