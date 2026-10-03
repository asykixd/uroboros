"""Inline-бот: формы с кнопками, списки и галереи для модулей (``self.inline``)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from ..errors import InlineError
from .manager import InlineManager
from .types import InlineCall, InlineMessage, InlineQuery

if TYPE_CHECKING:
    from ..loader import Loader
    from ..types import Module

__all__ = ["Inline", "InlineCall", "InlineError", "InlineManager", "InlineMessage", "InlineQuery"]


class Inline:
    """``self.inline`` в модуле. Формы, отправленные модулем, снимаются при его выгрузке.

    Кнопка — словарь с ``text`` и одним действием:

    - ``"callback": self.method`` (+ ``"args"``, ``"kwargs"``) — вызвать ``method(call, *args, **kwargs)``;
      ``"confirm": "Точно?"`` сначала спросит подтверждение;
    - ``"url": "https://..."`` — ссылка;
    - ``"input": "Подсказка", "handler": self.method`` — ввод текста, ``method(call, text, *args)``;
    - ``"data": "строка"`` — кнопка для ``@callback_handler``;
    - ``"action": "close"`` — удалить форму.

    ``buttons`` — список рядов кнопок, один ряд (список словарей) или одна кнопка.
    Нажимать кнопки может только владелец аккаунта и пользователи из ``always_allow``.
    """

    def __init__(self, loader: Loader, module: Module | None):
        self._loader = loader
        self._module = module

    @property
    def _manager(self) -> InlineManager:
        manager = self._loader.inline
        if manager is None:
            raise InlineError("Inline-бот не запущен")
        return manager

    @property
    def _stem(self) -> str | None:
        return getattr(self._module, "_stem", None)

    @property
    def available(self) -> bool:
        """Бот запущен и формы можно отправлять."""
        return self._loader.inline is not None and self._loader.inline.ready

    @property
    def bot(self) -> Any:
        """``aiogram.Bot`` — для всего, чего нет в этом API."""
        self._manager._require()
        return self._manager.bot

    @property
    def bot_username(self) -> str | None:
        return self._loader.inline.bot_username if self._loader.inline else None

    @property
    def bot_id(self) -> int | None:
        return self._loader.inline.bot_id if self._loader.inline else None

    def markup(self, buttons: Any, *, always_allow: list[int] | tuple[int, ...] = ()) -> Any:
        """Клавиатура из кнопок Uroboros для ``self.inline.bot.send_message(..., reply_markup=...)``.

        Колбэки работают так же, как в формах, и снимаются при выгрузке модуля.
        """
        return self._manager.markup(buttons, stem=self._stem, always_allow=always_allow)

    async def form(
        self,
        message: Any,
        text: str,
        buttons: Any = None,
        *,
        photo: str | None = None,
        always_allow: list[int] | tuple[int, ...] = (),
    ) -> InlineMessage:
        """Отправляет сообщение с кнопками вместо своего ``message`` (на чужое — ответом).

        ``photo`` — ссылка на картинку, тогда ``text`` становится подписью.
        """
        return await self._manager.form(message, text, buttons, stem=self._stem, photo=photo, always_allow=always_allow)

    async def list(
        self,
        message: Any,
        pages: list[str],
        *,
        buttons: Any = None,
        always_allow: list[int] | tuple[int, ...] = (),
    ) -> InlineMessage:
        """Форма со страницами ``pages``, листается кнопками ◀ ▶."""
        return await self._manager.list(message, pages, buttons=buttons, stem=self._stem, always_allow=always_allow)

    async def gallery(
        self,
        message: Any,
        photos: list[str] | Callable[[], Awaitable[str]],
        caption: str | list[str] = "",
        *,
        buttons: Any = None,
        always_allow: list[int] | tuple[int, ...] = (),
    ) -> InlineMessage:
        """Галерея: список ссылок на картинки (◀ ▶) или async-функция, которая отдаёт новую ссылку («Ещё»)."""
        return await self._manager.gallery(
            message, photos, caption, buttons=buttons, stem=self._stem, always_allow=always_allow
        )
