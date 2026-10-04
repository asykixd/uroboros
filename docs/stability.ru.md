# Стабильность API

С версии 1.0 Uroboros следует [semver](https://semver.org/lang/ru/): `МАЖОРНАЯ.МИНОРНАЯ.ПАТЧ`.

- **Патч** (`1.0.1`) — только исправления.
- **Минорная** (`1.1.0`) — новые возможности; написанные модули продолжают работать.
- **Мажорная** (`2.0.0`) — может удалять устаревшее. Перед ней — список изменений и инструкция.

Версии с флагом `-dev` (`1.1.0-dev`) — сборки из ветки `dev`: появившееся в них может ещё поменяться,
пока не попадёт в `master`. Гарантии выше относятся к версиям без флага.

## Что входит в публичный API

То, на что можно опираться в модулях:

- всё, что экспортирует `uroboros` (`Module`, `Library`, `ModuleConfig`, `ConfigValue`, `command`, `watcher`,
  `loop`, `StopLoop`, `inline_handler`, `callback_handler`, `LoadError`, `InlineError`, `utils`, `validators`);
- функции `uroboros.utils`, валидаторы `uroboros.validators`, исключения `uroboros.errors`;
- атрибуты и методы модуля: `client`, `db`, `loader`, `inline`, `config`, `strings`, `get`, `set`, `import_lib`,
  хуки `on_load`, `on_unload`, `on_dlmod`;
- `self.inline`: `form`, `list`, `gallery`, `markup`, `available`, `bot`; `InlineCall`, `InlineMessage`, `InlineQuery`;
- параметры декораторов и формат кнопок;
- шапка файла: `# meta`, `# requires`, `# requires_uroboros`.

Не входят: внутренности загрузчика, диспетчера и inline-менеджера (`self.loader.*` кроме списка модулей и команд),
модуль `uroboros.hikka` (адаптер следует за Hikka, а не за semver), всё, что начинается с `_`.

Сигнатуры публичного API зафиксированы в `tests/api_snapshot.json`: тест `tests/test_public_api.py` падает,
если что-то пропало или изменилось без обновления слепка.

## Устаревание

Ничего не удаляется сразу. Устаревшее имя:

1. помечается `uroboros.deprecation.deprecated(since=..., removed_in=..., alternative=...)`;
2. продолжает работать минимум одну минорную версию, выдавая `DeprecationWarning` и одно предупреждение в лог;
3. удаляется не раньше следующей мажорной версии и попадает в её список изменений.

```python
from uroboros.deprecation import deprecated

@deprecated(since="1.2", removed_in="2.0", alternative="utils.get_target")
def get_victim(message): ...
```
