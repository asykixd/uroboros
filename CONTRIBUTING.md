# Как помочь проекту

Спасибо, что хотите помочь! Интерфейс, сообщения бота, документация и коммиты — на русском.

## Ветки

- `dev` — разработка, сюда и присылайте pull request'ы;
- `master` — стабильные версии, попадают туда только из `dev` после проверки.

## Перед pull request'ом

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev,docs]'
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/python -m pytest
```

- Тесты не ходят в сеть и не требуют Telegram — новые тоже должны работать так.
- Публичный API зафиксирован в `tests/api_snapshot.json`, правила изменения — [docs/stability.md](docs/stability.md).
- Поменяли встроенную команду или пример — перегенерируйте справочник: `python scripts/gen_docs.py`.
- Сообщения бота — «карточками» через `utils.card(...)`, правила — в [docs/modules.md](docs/modules.md#оформление-ответов).

## Модули

Свои модули лучше держать в собственном репозитории — шаблон:
[uroboros-modules](https://github.com/asykixd/uroboros-modules). Полезные модули можно предложить туда.
