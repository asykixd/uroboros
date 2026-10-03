# Установка

Uroboros работает везде, где есть Python 3.10+. При первом запуске он пишет в консоль ссылку на
веб-панель входа: там вводятся `api_id` и `api_hash` (их выдают на https://my.telegram.org/apps),
номер, код и пароль 2FA — или сканируется QR-код. Вход в консоли: `--cli`.

Данные лежат в `data/` рядом с программой (путь меняется переменной `UROBOROS_DATA`).
Там сессия Telegram: это доступ к аккаунту, не показывайте её никому.

## Параметры запуска

| Параметр | Что делает |
|---|---|
| `--cli` | вход в консоли вместо веб-панели |
| `--host`, `--port` | адрес веб-панели входа (по умолчанию `127.0.0.1:8080`), или `UROBOROS_WEB_HOST`, `UROBOROS_WEB_PORT` |
| `UROBOROS_DATA` | каталог данных (по умолчанию `./data`) |
| `UROBOROS_API_ID`, `UROBOROS_API_HASH` | данные приложения Telegram вместо `config.json` |
| `UROBOROS_BOT_TOKEN` | свой inline-бот вместо созданного автоматически |

## Обновление

`.update` скачивает новости канала, показывает список изменений и ждёт подтверждения (`.update -f` — сразу).
Новая версия ставится вместе с зависимостями; если они не встали или новая версия не запускается, git
возвращается на прежнюю версию, и бот работает дальше.

- `.update channel beta` — каждый коммит в `master` (по умолчанию, пока нет 1.0);
- `.update channel stable` — только релизы (теги);
- `.update notify off` — не присылать раз в сутки уведомление о новой версии.

## Linux и VPS

```bash
curl -fsSL https://raw.githubusercontent.com/asykixd/uroboros/master/install.sh | sh
```

Скрипт проверит Python и git, склонирует репозиторий в `~/uroboros` (другой каталог — `UROBOROS_DIR`),
создаст виртуальное окружение и запустит бота. На Debian/Ubuntu может понадобиться
`sudo apt install git python3 python3-venv`.

На VPS без браузера откройте панель входа через SSH-туннель со своего компьютера:

```bash
ssh -L 8080:127.0.0.1:8080 пользователь@сервер
```

и перейдите по ссылке из консоли у себя в браузере.

### Служба systemd

```bash
sh ~/uroboros/install.sh --service
```

Установит user service `uroboros`. Первый вход сделайте вручную (`cd ~/uroboros && .venv/bin/python -m uroboros`),
затем:

```bash
systemctl --user enable --now uroboros
journalctl --user -u uroboros -f
sudo loginctl enable-linger $USER
```

Последняя команда нужна, чтобы служба работала, когда вы не залогинены. `.restart` и `.update`
перезапускают процесс на месте, systemd это не мешает.

## Termux (Android)

```bash
curl -fsSL https://raw.githubusercontent.com/asykixd/uroboros/master/install.sh | sh
```

В Termux скрипт поставит `python`, `git` и `rust`: Rust нужен, чтобы собрать `pydantic-core` для inline-бота,
сборка занимает несколько минут. Панель входа откройте в браузере на том же телефоне.

Автозапуск при включении телефона — через приложение [Termux:Boot](https://f-droid.org/packages/com.termux.boot/):

```bash
sh ~/uroboros/install.sh --boot
```

Termux:Boot запускает бота без терминала, поэтому первый вход нужно сделать вручную.

## Docker

```bash
git clone https://github.com/asykixd/uroboros && cd uroboros
docker compose up -d
docker compose logs -f
```

Ссылка на панель входа появится в логах; панель доступна только с этой машины (`127.0.0.1:8080`).
Данные — в `./data`. Обновление: `git pull && docker compose up -d --build` (`.update` в Docker не работает).

## Windows

1. Поставьте [Python 3.10+](https://www.python.org/downloads/) (галочка «Add python.exe to PATH») и [Git](https://git-scm.com/download/win).
2. В PowerShell:

```powershell
git clone https://github.com/asykixd/uroboros
cd uroboros
python -m venv .venv
.venv\Scripts\python -m pip install -e .
.venv\Scripts\python -m uroboros
```

Откройте ссылку из консоли в браузере. Окно консоли должно оставаться открытым: `.restart` и `.update`
перезапускают бота в нём же.

## macOS

```bash
brew install python git
curl -fsSL https://raw.githubusercontent.com/asykixd/uroboros/master/install.sh | sh
```

Или вручную, как на Linux: `git clone`, `python3 -m venv .venv`, `.venv/bin/pip install -e .`, `.venv/bin/python -m uroboros`.
