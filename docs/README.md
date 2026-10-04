# Uroboros

Модульный юзербот для Telegram на Python и Telethon. Команды и модули на русском, API модулей похож на Hikka,
а большинство модулей Hikka и FTG работают через встроенный адаптер.

- [Установка](install.md): Linux и VPS, служба systemd, Termux, Docker, Windows, macOS
- [Команды](commands.md): все встроенные команды и уровни доступа
- [Безопасность](security.md): кто может вызывать команды, проверка модулей, защита во время работы
- [Как писать модули](modules.md): команды и фильтры, вотчеры, фоновые задачи, хранилище, настройки, строки,
  библиотеки, inline-формы с кнопками, `utils`
- [Примеры модулей](examples.md): каждый пример загружается в тестах, так что они не устаревают
- [Модули Hikka и FTG](hikka.md): как работает адаптер, что поддерживается и что нет
- [Стабильность API](stability.md): semver, что входит в публичный API, политика устаревания
- [План развития](https://github.com/asykixd/uroboros/blob/master/ROADMAP.md)

Быстрый старт на Linux, macOS и в Termux:

```bash
curl -fsSL https://raw.githubusercontent.com/asykixd/uroboros/master/install.sh | sh
```

Бот откроет веб-панель входа: введите api_id и api_hash с [my.telegram.org](https://my.telegram.org), номер и код.
Потом напишите в любом чате `.help`.
