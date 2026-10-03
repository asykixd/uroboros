"""Базовый класс модуля и конфиг модуля."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from telethon import TelegramClient

    from .database import ModuleDB
    from .loader import Loader
    from .loops import Loop

CONFIG_KEY = "__config__"


class ConfigValue:
    def __init__(
        self,
        key: str,
        default: Any = None,
        doc: str = "",
        validator: Callable[[Any], Any] | None = None,
    ):
        self.key = key
        self.default = default
        self.doc = doc
        self.validator = validator

    def validate(self, value: Any) -> Any:
        return self.validator(value) if self.validator else value


class ModuleConfig:
    """Настройки модуля, которые пользователь меняет через .cfg.

    Значения хранятся в БД модуля под ключом ``__config__``.
    """

    def __init__(self, *values: ConfigValue):
        self._values = {value.key: value for value in values}
        self._db: ModuleDB | None = None

    def _bind(self, db: ModuleDB) -> None:
        self._db = db

    def _stored(self) -> dict[str, Any]:
        return self._db.get(CONFIG_KEY, {}) if self._db else {}

    def __getitem__(self, key: str) -> Any:
        value = self._values[key]
        return self._stored().get(key, value.default)

    def __setitem__(self, key: str, raw: Any) -> None:
        value = self._values[key].validate(raw)
        if self._db is None:
            raise RuntimeError("Конфиг ещё не привязан к модулю")
        stored = self._stored()
        stored[key] = value
        self._db.set(CONFIG_KEY, stored)

    def reset(self, key: str) -> None:
        if key not in self._values:
            raise KeyError(key)
        stored = self._stored()
        if stored.pop(key, None) is not None and self._db is not None:
            self._db.set(CONFIG_KEY, stored)

    def __contains__(self, key: object) -> bool:
        return key in self._values

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def value(self, key: str) -> ConfigValue:
        return self._values[key]


class Module:
    """Базовый класс модулей.

    Атрибуты ``client``, ``db``, ``loader`` проставляет загрузчик перед ``on_load``.
    """

    name: str = ""
    strings: ClassVar[dict[str, str]] = {}
    config: ModuleConfig | None = None

    client: TelegramClient
    db: ModuleDB
    loader: Loader

    # Служебное: из какого файла модуль и откуда он установлен.
    _stem: str
    _origin: str
    _meta: dict[str, str]  # из шапки файла: # meta developer: ..., # meta version: ...
    _loops: list[Loop]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not cls.__dict__.get("name"):
            cls.name = cls.__name__

    @property
    def is_builtin(self) -> bool:
        return self._origin == "builtin"

    def get(self, key: str, default: Any = None) -> Any:
        """Значение из хранилища модуля (то же, что ``self.db.get``)."""
        return self.db.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Записать значение в хранилище модуля (то же, что ``self.db.set``)."""
        self.db.set(key, value)

    async def import_lib(self, url: str, *, reload: bool = False) -> Any:
        """Подключает библиотеку по ссылке (GitHub-ссылки понимаются).

        Возвращает экземпляр класса-наследника ``Library`` из файла, а если его нет —
        сам Python-модуль. Исходник кешируется на диске: после рестарта сеть не нужна.
        ``reload=True`` скачивает библиотеку заново.
        """
        return await self.loader.import_lib(url, self, reload=reload)

    async def on_load(self) -> None:
        """Вызывается после загрузки модуля."""

    async def on_unload(self) -> None:
        """Вызывается перед выгрузкой модуля.

        При остановке и перезапуске клиент к этому моменту уже может быть отключён.
        """


class Library:
    """Базовый класс библиотеки: общий код для нескольких модулей.

    Модуль подключает её через ``await self.import_lib(url)`` и получает экземпляр.
    Одна библиотека живёт в одном экземпляре на всех; когда выгружен последний
    модуль, который её подключил, она выгружается сама.
    """

    name: str = ""

    client: TelegramClient
    db: ModuleDB
    loader: Loader

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not cls.__dict__.get("name"):
            cls.name = cls.__name__

    async def on_load(self) -> None:
        """Вызывается после загрузки библиотеки."""

    async def on_unload(self) -> None:
        """Вызывается перед выгрузкой библиотеки."""
