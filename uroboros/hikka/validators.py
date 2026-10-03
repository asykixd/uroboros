"""Валидаторы Hikka (``loader.validators``): объект с ``validate(value)``, ``doc`` и ``internal_id``.

Поведение повторяет Hikka (AGPL-3.0, https://github.com/hikariatama/Hikka), подсказки — на русском.
"""

from __future__ import annotations

import re
import typing
import urllib.parse

from .. import validators as core

ConfigAllowedTypes = tuple | list | str | int | bool | None


class ValidationError(core.ValidationError):
    """Значение не подходит. Текст показывается в ``.cfg``."""


class Validator:
    def __init__(self, validator: typing.Callable[[typing.Any], typing.Any], doc: typing.Any = None, _internal_id=None):
        self.validate = validator
        if isinstance(doc, str) or doc is None:
            doc = {"ru": doc or "любое значение", "en": doc or "any value"}
        self.doc = doc
        self.internal_id = _internal_id


def doc_of(validator: typing.Any) -> str:
    doc = getattr(validator, "doc", "")
    if isinstance(doc, dict):
        return doc.get("ru") or doc.get("en") or next(iter(doc.values()), "")
    return str(doc or "")


_TRUE = ["True", "true", "1", 1, True, "yes", "Yes", "on", "On", "y", "Y", "да", "вкл"]
_FALSE = ["False", "false", "0", 0, False, "no", "No", "off", "Off", "n", "N", "нет", "выкл"]


class Boolean(Validator):
    def __init__(self):
        super().__init__(self._validate, "логическим значением (да / нет)", _internal_id="Boolean")

    @staticmethod
    def _validate(value, /):
        if value not in _TRUE + _FALSE:
            raise ValidationError("Нужно да или нет")
        return value in _TRUE


class Integer(Validator):
    def __init__(self, *, digits=None, minimum=None, maximum=None):
        parts = ["целым числом"]
        if minimum is not None:
            parts.append(f"не меньше {minimum}")
        if maximum is not None:
            parts.append(f"не больше {maximum}")
        if digits is not None:
            parts.append(f"из {digits} цифр")
        super().__init__(
            lambda value: self._validate(value, digits=digits, minimum=minimum, maximum=maximum),
            ", ".join(parts),
            _internal_id="Integer",
        )

    @staticmethod
    def _validate(value, /, *, digits, minimum, maximum):
        try:
            value = int(str(value).strip())
        except ValueError:
            raise ValidationError(f"Нужно целое число, а не {value}") from None
        if minimum is not None and value < minimum:
            raise ValidationError(f"Минимум — {minimum}")
        if maximum is not None and value > maximum:
            raise ValidationError(f"Максимум — {maximum}")
        if digits is not None and len(str(value)) != digits:
            raise ValidationError(f"Нужно ровно {digits} цифр")
        return value


class Float(Validator):
    def __init__(self, *, minimum=None, maximum=None):
        parts = ["числом"]
        if minimum is not None:
            parts.append(f"не меньше {minimum}")
        if maximum is not None:
            parts.append(f"не больше {maximum}")
        super().__init__(
            lambda value: self._validate(value, minimum=minimum, maximum=maximum),
            ", ".join(parts),
            _internal_id="Float",
        )

    @staticmethod
    def _validate(value, /, *, minimum, maximum):
        try:
            value = float(str(value).strip().replace(",", "."))
        except ValueError:
            raise ValidationError(f"Нужно число, а не {value}") from None
        if minimum is not None and value < minimum:
            raise ValidationError(f"Минимум — {minimum}")
        if maximum is not None and value > maximum:
            raise ValidationError(f"Максимум — {maximum}")
        return value


class Choice(Validator):
    def __init__(self, possible_values: list):
        self.possible_values = list(possible_values)
        super().__init__(
            lambda value: self._validate(value, possible_values=self.possible_values),
            "одним из: " + ", ".join(map(str, self.possible_values)),
            _internal_id="Choice",
        )

    @staticmethod
    def _validate(value, /, *, possible_values):
        for option in possible_values:
            if value == option or str(value) == str(option):
                return option
        raise ValidationError("Допустимые значения: " + ", ".join(map(str, possible_values)))


class MultiChoice(Validator):
    def __init__(self, possible_values: list):
        self.possible_values = list(possible_values)
        super().__init__(
            lambda value: self._validate(value, possible_values=self.possible_values),
            "списком из: " + ", ".join(map(str, self.possible_values)),
            _internal_id="MultiChoice",
        )

    @staticmethod
    def _validate(value, /, *, possible_values):
        if not isinstance(value, (list, tuple)):
            value = [value]
        for item in value:
            if item not in possible_values:
                raise ValidationError("Допустимые значения: " + ", ".join(map(str, possible_values)))
        return list(dict.fromkeys(value))


class Series(Validator):
    def __init__(self, validator=None, min_len=None, max_len=None, fixed_len=None):
        self.validator = validator
        each = f" (каждое — {doc_of(validator)})" if validator is not None else ""
        super().__init__(
            lambda value: self._validate(
                value, validator=validator, min_len=min_len, max_len=max_len, fixed_len=fixed_len
            ),
            "списком значений через запятую" + each,
            _internal_id="Series",
        )

    @staticmethod
    def _validate(value, /, *, validator, min_len, max_len, fixed_len):
        if isinstance(value, str):
            value = [item for item in value.split(",") if item.strip()] if value.strip() else []
        if not isinstance(value, (list, tuple, set)):
            value = [value]
        value = [item.strip() if isinstance(item, str) else item for item in value]
        if min_len is not None and len(value) < min_len:
            raise ValidationError(f"Нужно хотя бы {min_len} значений")
        if max_len is not None and len(value) > max_len:
            raise ValidationError(f"Можно не больше {max_len} значений")
        if fixed_len is not None and len(value) != fixed_len:
            raise ValidationError(f"Нужно ровно {fixed_len} значений")
        if validator is not None:
            value = [validator.validate(item) for item in value]
        return value


class String(Validator):
    def __init__(self, length=None, min_len=None, max_len=None):
        if length is not None:
            doc = f"строкой длиной {length}"
        elif min_len is not None and max_len is not None:
            doc = f"строкой длиной от {min_len} до {max_len}"
        elif min_len is not None:
            doc = f"строкой не короче {min_len}"
        elif max_len is not None:
            doc = f"строкой не длиннее {max_len}"
        else:
            doc = "строкой"
        super().__init__(
            lambda value: self._validate(value, length=length, min_len=min_len, max_len=max_len),
            doc,
            _internal_id="String",
        )

    @staticmethod
    def _validate(value, /, *, length, min_len, max_len):
        if isinstance(value, (list, tuple)):
            value = " ".join(map(str, value))
        value = str(value)
        if length is not None and len(value) != length:
            raise ValidationError(f"Нужна строка длиной {length}")
        if min_len is not None and len(value) < min_len:
            raise ValidationError(f"Минимальная длина — {min_len}")
        if max_len is not None and len(value) > max_len:
            raise ValidationError(f"Максимальная длина — {max_len}")
        return value


class Link(Validator):
    def __init__(self):
        super().__init__(self._validate, "ссылкой", _internal_id="Link")

    @staticmethod
    def _validate(value, /):
        parsed = urllib.parse.urlparse(str(value))
        if not parsed.scheme or not parsed.netloc:
            raise ValidationError(f"Это не ссылка: {value}")
        return str(value)


class RegExp(Validator):
    def __init__(self, regex: str, flags=None, description=None):
        flags = flags or 0
        if isinstance(description, dict):
            description = description.get("ru") or description.get("en")
        super().__init__(
            lambda value: self._validate(value, regex=regex, flags=flags),
            description or f"строкой по шаблону {regex}",
            _internal_id="RegExp",
        )

    @staticmethod
    def _validate(value, /, *, regex, flags):
        if not re.match(regex, str(value), flags=flags):
            raise ValidationError(f"Значение должно подходить под шаблон {regex}")
        return str(value)


class TelegramID(Validator):
    def __init__(self):
        super().__init__(self._validate, "id в Telegram", _internal_id="TelegramID")

    @staticmethod
    def _validate(value, /):
        text = str(value).strip()
        if text.startswith("-100"):
            text = text[4:]
        try:
            value = int(text)
        except ValueError:
            raise ValidationError(f"Это не id: {value}") from None
        if not 0 <= value <= 2**64 - 1:
            raise ValidationError(f"Это не id: {value}")
        return value


class Union(Validator):
    def __init__(self, *validators):
        self.validators = validators
        super().__init__(
            lambda value: self._validate(value, validators=validators),
            " или ".join(doc_of(v) for v in validators),
            _internal_id="Union",
        )

    @staticmethod
    def _validate(value, /, *, validators):
        for validator in validators:
            try:
                return validator.validate(value)
            except ValidationError:
                continue
        raise ValidationError(f"Значение не подходит: {value}")


class NoneType(Validator):
    def __init__(self):
        super().__init__(self._validate, "пустым значением", _internal_id="NoneType")

    @staticmethod
    def _validate(value, /):
        if value:
            raise ValidationError("Нужно пустое значение")
        return None


class Hidden(Validator):
    def __init__(self, validator=None):
        validator = validator or String()
        self.validator = validator
        super().__init__(validator.validate, doc_of(validator), _internal_id="Hidden")


class Emoji(Validator):
    def __init__(self, length=None, min_len=None, max_len=None):
        super().__init__(
            lambda value: self._validate(value, length=length, min_len=min_len, max_len=max_len),
            "эмодзи",
            _internal_id="Emoji",
        )

    @staticmethod
    def _validate(value, /, *, length, min_len, max_len):
        value = str(value)
        if any(ch.isalnum() for ch in value):
            raise ValidationError("Нужны только эмодзи")
        count = len([ch for ch in value if not 0xFE00 <= ord(ch) <= 0xFE0F and ch != "‍"])
        if length is not None and count != length:
            raise ValidationError(f"Нужно {length} эмодзи")
        if min_len is not None and count < min_len:
            raise ValidationError(f"Нужно хотя бы {min_len} эмодзи")
        if max_len is not None and count > max_len:
            raise ValidationError(f"Можно не больше {max_len} эмодзи")
        return value


class EntityLike(RegExp):
    def __init__(self):
        super().__init__(
            r"^(?:@|https?://t\.me/)?[a-zA-Z0-9_]{4,32}$|^-?\d+$",
            description="@username, ссылкой или id",
        )
