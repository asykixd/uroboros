import logging

import pytest

from uroboros import logs

SAMPLE = """\
2026-10-03 10:00:00,001 [INFO] uroboros: Готов
2026-10-03 10:00:01,002 [ERROR] uroboros.dispatcher: Ошибка в команде x
Traceback (most recent call last):
  File "x.py", line 1
ValueError: boom
2026-10-03 10:00:02,003 [WARNING] uroboros.loader: Файл пропал
"""


@pytest.mark.parametrize(
    ("name", "level"),
    [("error", 40), ("WARN", 30), ("Warning", 30), ("10", 10), ("nope", None)],
)
def test_parse_level(name, level):
    assert logs.parse_level(name) == level


def test_filter_keeps_traceback_with_its_record():
    lines = logs.filter_records(SAMPLE, logging.ERROR)
    assert lines[0].endswith("Ошибка в команде x")
    assert lines[-1] == "ValueError: boom"
    assert len(lines) == 4


def test_filter_all_levels():
    assert len(logs.filter_records(SAMPLE, logging.NOTSET)) == 6
