---
name: release
description: Выпустить pre-release Uroboros (X.Y.Z-dev): версия, тег, GitHub-релиз с заметками на русском.
disable-model-invocation: true
---

# Релиз Uroboros

Делать только по прямой просьбе пользователя. До 1.0 каждый релиз — с dev-флагом.

1. **Номер версии.** Посмотри текущую версию в `pyproject.toml` и последние теги (`git tag --sort=-creatordate | head`). Предложи номер `X.Y.Z-dev` и **дождись подтверждения пользователя**. Без `-dev` — только 1.0 и дальше.
2. **Проверки локально** (минуты GitHub Actions могут быть исчерпаны — не полагайся на CI):
   ```bash
   .venv/bin/ruff check . && .venv/bin/ruff format --check .
   .venv/bin/python -m pytest -q
   ```
   Если `gh run list --branch master -L 1` показывает выполненный прогон — он должен быть зелёным.
3. **Версия в двух местах:** `pyproject.toml` (`version = "X.Y.Z-dev"`) и `uroboros/__init__.py` (`__version__`). Версия не должна быть меньше любого `# requires_uroboros:` в `examples/` (`grep -r requires_uroboros examples/`).
4. **ROADMAP.md:** сделанное в этапе отмечено `[x]`.
5. **Коммит** `Версия X.Y.Z-dev` (с attribution-строкой из системных инструкций), push в `master`.
6. **Тег:** `git tag -a vX.Y.Z-dev -m "Uroboros X.Y.Z-dev"` и `git push origin vX.Y.Z-dev`.
7. **GitHub-релиз:** заметки на русском по коммитам с прошлого тега (`git log <прошлый-тег>..HEAD --oneline`), сгруппировать: новое, адаптер Hikka, исправления, для авторов модулей. Затем
   ```bash
   gh release create vX.Y.Z-dev --prerelease --title "Uroboros X.Y.Z-dev" --notes-file <файл>
   ```
8. Показать пользователю ссылку на релиз.
