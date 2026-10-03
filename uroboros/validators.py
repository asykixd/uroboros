"""Валидаторы значений ModuleConfig.

Валидатор принимает уже типизированное значение или строку (из команды .cfg)
и возвращает приведённое значение либо бросает ValidationError.
"""

from __future__ import annotations

from typing import Any, Iterable


class ValidationError(ValueError):
    pass


class Validator:
    doc = "любое значение"

    def __call__(self, value: Any) -> Any:
        return value


class String(Validator):
    def __init__(self, min_len: int | None = None, max_len: int | None = None):
        self.min_len, self.max_len = min_len, max_len
        self.doc = "строка"

    def __call__(self, value: Any) -> str:
        value = str(value)
        if self.min_len is not None and len(value) < self.min_len:
            raise ValidationError(f"Минимальная длина — {self.min_len}")
        if self.max_len is not None and len(value) > self.max_len:
            raise ValidationError(f"Максимальная длина — {self.max_len}")
        return value


class Integer(Validator):
    def __init__(self, minimum: int | None = None, maximum: int | None = None):
        self.minimum, self.maximum = minimum, maximum
        self.doc = "целое число"

    def __call__(self, value: Any) -> int:
        if isinstance(value, bool):
            raise ValidationError("Нужно целое число")
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise ValidationError("Нужно целое число") from None
        if self.minimum is not None and value < self.minimum:
            raise ValidationError(f"Минимум — {self.minimum}")
        if self.maximum is not None and value > self.maximum:
            raise ValidationError(f"Максимум — {self.maximum}")
        return value


class Float(Validator):
    doc = "число"

    def __call__(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            raise ValidationError("Нужно число") from None


_TRUE = {"1", "true", "yes", "on", "да", "вкл"}
_FALSE = {"0", "false", "no", "off", "нет", "выкл"}


class Boolean(Validator):
    doc = "да / нет"

    def __call__(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in _TRUE:
            return True
        if text in _FALSE:
            return False
        raise ValidationError("Нужно да/нет")


class Choice(Validator):
    def __init__(self, options: Iterable[Any]):
        self.options = list(options)
        self.doc = "одно из: " + ", ".join(map(str, self.options))

    def __call__(self, value: Any) -> Any:
        for option in self.options:
            if value == option or str(value) == str(option):
                return option
        raise ValidationError("Допустимые значения: " + ", ".join(map(str, self.options)))
