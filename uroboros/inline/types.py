"""Формы, кнопки и обёртки над колбэками и inline-запросами."""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..errors import InlineError

if TYPE_CHECKING:
    from .manager import InlineManager

# Ключи кнопки, которые определяют её действие; ровно один на кнопку.
ACTION_KEYS = ("callback", "url", "input", "data", "action")
ACTIONS = ("close",)

Buttons = list[list[dict[str, Any]]]


class _Keep:
    def __repr__(self) -> str:
        return "KEEP"


KEEP: Any = _Keep()  # «не менять кнопки» в edit


def normalize_buttons(buttons: Any) -> Buttons:
    """Кнопки в виде рядов: ``dict`` — одна кнопка, список словарей — один ряд, список списков — ряды."""
    if not buttons:
        return []
    if isinstance(buttons, dict):
        rows = [[buttons]]
    elif all(isinstance(item, dict) for item in buttons):
        rows = [list(buttons)]
    else:
        rows = [[item] if isinstance(item, dict) else list(item) for item in buttons]

    for row in rows:
        for button in row:
            if not isinstance(button, dict) or not isinstance(button.get("text"), str):
                raise InlineError(f"У кнопки должен быть текст: {button!r}")
            actions = [key for key in ACTION_KEYS if key in button]
            if len(actions) != 1:
                raise InlineError(
                    f"У кнопки «{button['text']}» должно быть ровно одно действие: {', '.join(ACTION_KEYS)}"
                )
            if "input" in button and not callable(button.get("handler")):
                raise InlineError(f"Кнопке ввода «{button['text']}» нужен handler")
            if "callback" in button and not callable(button["callback"]):
                raise InlineError(f"callback кнопки «{button['text']}» нельзя вызвать")
            if "action" in button and button["action"] not in ACTIONS:
                raise InlineError(f"Неизвестное действие кнопки: {button['action']}")
            if "data" in button and not 1 <= len(str(button["data"]).encode()) <= 64:
                raise InlineError("data кнопки — от 1 до 64 байт")
    return [row for row in rows if row]


@dataclass(eq=False)
class Unit:
    """Одно сообщение с кнопками от inline-бота (форма, список, галерея)."""

    id: str
    stem: str | None  # файл модуля-владельца: при его выгрузке кнопки снимаются
    text: str
    buttons: Buttons
    photo: str | None = None
    title: str | None = None  # для inline-результатов
    description: str | None = None
    allowed: frozenset[int] = frozenset()  # кроме владельца
    inline_message_id: str | None = None
    bot_message: tuple[int, int] | None = None  # (chat_id, message_id), если сообщение отправил сам бот
    user_message: tuple[int, int] | None = None  # то же сообщение со стороны юзербота
    created: float = field(default_factory=time.monotonic)
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    keys: list[str] = field(default_factory=list)  # callback_data и id полей ввода текущих кнопок


class InlineMessage:
    """Отправленная форма: её можно изменить или удалить."""

    def __init__(self, manager: InlineManager, unit: Unit):
        self._manager = manager
        self.unit = unit

    @property
    def id(self) -> str:
        return self.unit.id

    @property
    def inline_message_id(self) -> str | None:
        return self.unit.inline_message_id

    async def edit(self, text: str | None = None, buttons: Any = KEEP, *, photo: str | None = None) -> None:
        """Меняет текст и кнопки. ``buttons=None`` убирает кнопки, без аргумента — оставляет как были."""
        await self._manager.edit(self.unit, text, buttons, photo=photo)
        self._edited()

    async def delete(self) -> None:
        """Удаляет сообщение и снимает его кнопки."""
        await self._manager.delete(self.unit)

    def unload(self) -> None:
        """Снимает кнопки, сообщение остаётся (нажатия будут отвечать «кнопка устарела»)."""
        self._manager.drop(self.unit)

    def _edited(self) -> None:
        pass


class InlineCall(InlineMessage):
    """Нажатие кнопки. Передаётся в ``callback`` кнопки и в ``@callback_handler``.

    ``query`` — исходный ``CallbackQuery`` aiogram (для поля ввода — None).
    """

    def __init__(self, manager: InlineManager, unit: Unit, query: Any = None, *, data: str | None = None):
        super().__init__(manager, unit)
        self.query = query
        self.data = data if data is not None else getattr(query, "data", None)
        self.from_user = getattr(query, "from_user", None)
        self.answered = query is None
        self.edited = False

    def _edited(self) -> None:
        self.edited = True

    async def answer(self, text: str | None = None, *, show_alert: bool = False) -> None:
        """Ответ на нажатие: всплывающая подсказка, ``show_alert`` — окно с кнопкой OK."""
        if self.answered:
            return
        self.answered = True
        from aiogram.exceptions import TelegramBadRequest

        # Через 15 секунд после нажатия Telegram уже не принимает ответ — это не ошибка модуля.
        with contextlib.suppress(TelegramBadRequest):
            await self._manager.bot.answer_callback_query(self.query.id, text=text, show_alert=show_alert)


class InlineQuery:
    """Inline-запрос ``@бот имя аргументы`` для ``@inline_handler``."""

    def __init__(self, query: Any, args: str):
        self.query = query
        self.text = query.query
        self.args = args
        self.from_user = query.from_user
