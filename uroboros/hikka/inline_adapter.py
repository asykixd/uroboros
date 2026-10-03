"""``self.inline`` и нажатия кнопок с API Hikka поверх inline-бота Uroboros."""

from __future__ import annotations

import inspect
import logging
from types import SimpleNamespace
from typing import Any

from ..errors import InlineError

log = logging.getLogger(__name__)


def _wrap_callback(func: Any) -> Any:
    async def callback(call: Any, *args: Any, **kwargs: Any) -> Any:
        return await func(HikkaCall(call), *args, **kwargs)

    callback.__name__ = getattr(func, "__name__", "callback")
    return callback


def convert_markup(markup: Any) -> list:
    """Кнопки Hikka → кнопки Uroboros: колбэки получают ``HikkaCall``, ``action`` unload/answer — колбэки."""
    if not markup:
        return []
    if isinstance(markup, dict):
        rows = [[markup]]
    elif all(isinstance(item, dict) for item in markup):
        rows = [list(markup)]
    else:
        rows = [[item] if isinstance(item, dict) else list(item) for item in markup]

    result = []
    for row in rows:
        line = []
        for button in row:
            if not isinstance(button, dict):
                continue
            button = {k: v for k, v in button.items() if k not in ("force_me", "disable_security", "always_allow")}
            action = button.get("action")
            if action == "unload" and "callback" not in button:
                button.pop("action")
                button["callback"] = _unload_callback
            elif action == "answer" and "callback" not in button:
                button.pop("action")
                text, alert = button.pop("message", ""), button.pop("show_alert", False)
                button["callback"] = _answer_callback
                button["args"] = (text, alert)
            elif "callback" in button:
                button.pop("action", None)
                button["callback"] = _wrap_callback(button["callback"])
            if "input" in button and callable(button.get("handler")):
                button["handler"] = _wrap_callback(button["handler"])
            button.pop("style", None)
            button.pop("emoji", None)
            line.append(button)
        if line:
            result.append(line)
    return result


async def _unload_callback(call: Any) -> None:
    call.unload()
    await call.answer()


async def _answer_callback(call: Any, text: str, show_alert: bool) -> None:
    await call.answer(text, show_alert=show_alert)


class HikkaCall:
    """Нажатие кнопки в стиле Hikka: ``edit(text, reply_markup=...)``, ``answer``, ``delete``, ``unload``.

    Как в Hikka, ``edit`` без ``reply_markup`` убирает кнопки. Неизвестные атрибуты берутся
    из ``CallbackQuery`` aiogram.
    """

    def __init__(self, call: Any):
        self._call = call

    def __getattr__(self, name: str) -> Any:
        query = self.__dict__["_call"].query
        if query is not None:
            return getattr(query, name)
        raise AttributeError(name)

    @property
    def data(self) -> Any:
        return self._call.data

    @property
    def from_user(self) -> Any:
        return self._call.from_user

    @property
    def inline_message_id(self) -> Any:
        return self._call.inline_message_id

    @property
    def unit_id(self) -> str:
        return self._call.unit.id

    @property
    def form(self) -> dict:
        unit = self._call.unit
        return {"id": unit.id, "uid": unit.id, "text": unit.text, "buttons": unit.buttons}

    async def edit(
        self,
        text: str | None = None,
        reply_markup: Any = None,
        *,
        photo: str | None = None,
        gif: str | None = None,
        **_: Any,
    ) -> HikkaCall | bool:
        try:
            await self._call.edit(text, convert_markup(reply_markup), photo=photo or gif)
        except InlineError as e:
            log.warning("Не удалось изменить форму: %s", e)
            return False
        return self

    async def answer(self, text: str | None = None, show_alert: bool = False, **_: Any) -> None:
        await self._call.answer(text, show_alert=show_alert)

    async def delete(self) -> bool:
        await self._call.delete()
        return True

    async def unload(self) -> bool:
        self._call.unload()
        return True


class HikkaInlineMessage:
    """Результат ``self.inline.form`` в стиле Hikka."""

    def __init__(self, message: Any):
        self._message = message

    @property
    def unit_id(self) -> str:
        return self._message.id

    @property
    def inline_message_id(self) -> Any:
        return self._message.inline_message_id

    async def edit(self, text: str | None = None, reply_markup: Any = None, *, photo: str | None = None, **_: Any):
        try:
            await self._message.edit(text, convert_markup(reply_markup), photo=photo)
        except InlineError as e:
            log.warning("Не удалось изменить форму: %s", e)
            return False
        return self

    async def delete(self) -> bool:
        await self._message.delete()
        return True

    async def unload(self) -> bool:
        self._message.unload()
        return True


def _target(message: Any) -> Any:
    """Hikka разрешает вместо сообщения передать id чата: тогда форма просто отправляется туда."""
    if isinstance(message, int):
        return SimpleNamespace(out=False, chat_id=message, id=None, reply_to_msg_id=None, sender_id=None)
    return message


class HikkaInline:
    """``self.inline`` модуля Hikka."""

    def __init__(self, inline: Any):
        self._inline = inline  # uroboros.inline.Inline этого модуля

    @property
    def bot(self) -> Any:
        return self._inline.bot

    @property
    def _bot(self) -> Any:
        return self._inline.bot

    @property
    def bot_username(self) -> str | None:
        return self._inline.bot_username

    @property
    def bot_id(self) -> int | None:
        return self._inline.bot_id

    @property
    def init_complete(self) -> bool:
        return self._inline.available

    def generate_markup(self, markup_obj: Any) -> Any:
        from aiogram.types import InlineKeyboardMarkup

        if not markup_obj or isinstance(markup_obj, str):
            return None
        if isinstance(markup_obj, InlineKeyboardMarkup):
            return markup_obj
        return self._inline.markup(convert_markup(markup_obj))

    _generate_markup = generate_markup

    async def form(
        self,
        text: str,
        message: Any,
        reply_markup: Any = None,
        *,
        always_allow: list | None = None,
        disable_security: bool = False,
        photo: str | None = None,
        gif: str | None = None,
        **_: Any,
    ) -> HikkaInlineMessage | bool:
        manager = self._inline._manager
        try:
            sent = await manager.form(
                _target(message),
                text,
                convert_markup(reply_markup),
                stem=self._inline._stem,
                photo=photo or gif,
                always_allow=always_allow or (),
                public=disable_security,
            )
        except InlineError as e:
            log.warning("Форма не отправлена: %s", e)
            return False
        return HikkaInlineMessage(sent)

    async def list(
        self,
        message: Any,
        strings: list[str],
        *,
        always_allow: list | None = None,
        custom_buttons: Any = None,
        **_: Any,
    ) -> HikkaInlineMessage | bool:
        manager = self._inline._manager
        try:
            sent = await manager.list(
                _target(message),
                list(strings),
                buttons=convert_markup(custom_buttons),
                stem=self._inline._stem,
                always_allow=always_allow or (),
            )
        except InlineError as e:
            log.warning("Список не отправлен: %s", e)
            return False
        return HikkaInlineMessage(sent)

    async def gallery(
        self,
        message: Any,
        next_handler: Any,
        caption: Any = "",
        *,
        always_allow: list | None = None,
        custom_buttons: Any = None,
        **_: Any,
    ) -> HikkaInlineMessage | bool:
        photos = next_handler
        if callable(next_handler):

            async def photos() -> str:
                result = next_handler()
                if inspect.isawaitable(result):
                    result = await result
                return result[0] if isinstance(result, list) else result

        if callable(caption):
            caption = caption() if not inspect.iscoroutinefunction(caption) else await caption()
        manager = self._inline._manager
        try:
            sent = await manager.gallery(
                _target(message),
                photos,
                caption,
                buttons=convert_markup(custom_buttons),
                stem=self._inline._stem,
                always_allow=always_allow or (),
            )
        except InlineError as e:
            log.warning("Галерея не отправлена: %s", e)
            return False
        return HikkaInlineMessage(sent)


class HikkaInlineQuery:
    """Inline-запрос в стиле Hikka: ``query.args``, ``query.answer(...)``, ``e400()`` и т.п."""

    def __init__(self, query: Any):
        self._query = query  # uroboros.inline.InlineQuery

    def __getattr__(self, name: str) -> Any:
        return getattr(self.__dict__["_query"].query, name)

    @property
    def args(self) -> str:
        return self._query.args

    @property
    def query(self) -> str:
        return self._query.text

    @property
    def inline_query(self) -> Any:
        return self._query.query

    async def answer(self, results: Any, cache_time: int = 0, **kwargs: Any) -> Any:
        self._query.answered = True
        kwargs.setdefault("is_personal", True)
        return await self._query.query.answer(results, cache_time=cache_time, **kwargs)

    async def _error(self, title: str, description: str) -> None:
        from aiogram.types import InlineQueryResultArticle, InputTextMessageContent

        await self.answer(
            [
                InlineQueryResultArticle(
                    id="error",
                    title=title,
                    description=description,
                    input_message_content=InputTextMessageContent(message_text=f"❌ {title}"),
                )
            ]
        )

    async def e400(self) -> None:
        await self._error("Неверный запрос", "Проверьте аргументы")

    async def e403(self) -> None:
        await self._error("Нет доступа", "Эта команда вам недоступна")

    async def e404(self) -> None:
        await self._error("Ничего не найдено", "По этому запросу результатов нет")

    async def e426(self) -> None:
        await self._error("Нужно обновление", "Модулю нужна более новая версия")

    async def e500(self) -> None:
        await self._error("Ошибка", "Подробности в логах")


def convert_inline_results(raw: Any) -> Any:
    """Результаты ``@inline_handler`` Hikka → формат Uroboros (``reply_markup`` → ``buttons``)."""
    if raw is None:
        return None
    items = [raw] if isinstance(raw, dict) else list(raw)
    converted = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item = dict(item)
        item["buttons"] = convert_markup(item.pop("reply_markup", None) or item.get("buttons"))
        if item.get("gif") and not item.get("photo"):
            item["photo"] = item.pop("gif")
        if item.pop("disable_security", False):
            item["public"] = True
        converted.append(item)
    return converted
