---
name: api-change
description: Чек-лист при изменении публичного API Uroboros (всё, что экспортирует uroboros/__init__.py, utils, декораторы, Module, inline, config). Использовать при любой правке, которая меняет сигнатуры или поведение публичного API.
---

# Изменение публичного API

Публичный API — то, что экспортирует `uroboros/__init__.py` (см. раздел «API модулей» в CLAUDE.md). Политика — `docs/stability.md`.

1. **Совместимость.** Удалять или менять сигнатуру нельзя молча: старое поведение оставляется через `uroboros.deprecation.deprecated` с предупреждением. Новое — только добавлять.
2. **Слепок API.** После сознательного изменения:
   ```bash
   UPDATE_API_SNAPSHOT=1 .venv/bin/python -m pytest tests/test_public_api.py
   ```
   Посмотри дифф `tests/api_snapshot.json` — в нём должно быть только задуманное.
3. **Документация.** Обнови `docs/modules.md` (примеры там не форматируются ruff — проверь их глазами).
4. **Примеры.** `examples/*.py` загружаются в `tests/test_examples.py`. Если нужен новый API — добавь `# requires_uroboros: X` и проверь, что `__version__` в `dev` не меньше X.
5. **Адаптер Hikka.** API намеренно повторяет Hikka. Проверь шимы в `uroboros/hikka/` (`utils`, `loader`, inline), если менялись `utils.answer`, `strings`, `config` или inline-формы.
6. **Встроенные модули** (`uroboros/modules/`) пишутся только на публичном API — убедись, что они не лезут во внутренности.
7. **Тесты:**
   ```bash
   .venv/bin/python -m pytest -q && .venv/bin/ruff check . && .venv/bin/ruff format --check .
   ```
