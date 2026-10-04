---
name: release
description: Выпустить релиз Uroboros из master: тег vX.Y.Z и GitHub-релиз с заметками на русском.
disable-model-invocation: true
---

# Релиз Uroboros

Делать только по прямой просьбе пользователя. Релиз выходит **из `master`**, версия без `-dev`.

1. **Сначала `/promote`**, если в `dev` есть то, что должно войти в релиз (`git log --oneline master..dev`).
2. **Номер версии.** Он уже стоит в `master` (`pyproject.toml`, `uroboros/__init__.py`). Сверь с последними тегами (`git tag --sort=-creatordate | head`) и **подтверди у пользователя**.
3. **Проверки локально** в `master` (минуты GitHub Actions могут быть исчерпаны — не полагайся на CI):
   ```bash
   .venv/bin/ruff check . && .venv/bin/ruff format --check .
   .venv/bin/python -m pytest -q
   ```
   Если `gh run list --branch master -L 1` показывает выполненный прогон — он должен быть зелёным.
4. **ROADMAP.md:** сделанное в этапе отмечено `[x]` (правка — в `dev`, затем `/promote`).
5. **Тег:** `git tag -a vX.Y.Z -m "Uroboros X.Y.Z"` на коммите `master`, `git push origin vX.Y.Z`.
6. **GitHub-релиз:** заметки на русском по коммитам с прошлого релиза (`git log <прошлый-тег>..master --oneline --no-merges`), сгруппировать: новое, адаптер Hikka, исправления, для авторов модулей. Затем
   ```bash
   gh release create vX.Y.Z --title "Uroboros X.Y.Z" --notes-file <файл>
   ```
7. Показать пользователю ссылку на релиз и вернуться в `dev`.
