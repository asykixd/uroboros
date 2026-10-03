"""Inline-бот на aiogram 3 в том же процессе, что и юзербот.

Как показывается форма: юзербот делает inline-запрос к своему боту с id формы,
бот отвечает результатом с текстом и кнопками, юзербот отправляет этот результат
в чат. Нажатия приходят боту как ``callback_query``. Чтобы менять форму без нажатия,
нужен ``inline_message_id`` — его бот получает из ``chosen_inline_result``
(inline feedback, включается через @BotFather).

Ввод текста: кнопка подставляет в поле ввода ``@бот <id> ``, пользователь дописывает
значение и выбирает результат. Бот получает текст из ``chosen_inline_result``, а
служебное сообщение, которое при этом ушло в чат, юзербот сразу удаляет.
"""

from __future__ import annotations

import asyncio
import contextlib
import html
import logging
import os
import re
import secrets
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest, TelegramUnauthorizedError
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InlineQueryResultPhoto,
    InputMediaPhoto,
    InputTextMessageContent,
)
from telethon import events

from ..database import Database
from ..errors import InlineError, LoadError
from . import botfather
from .types import KEEP, InlineCall, InlineMessage, InlineQuery, Unit, normalize_buttons

if TYPE_CHECKING:
    from telethon import TelegramClient

    from ..loader import Loader

log = logging.getLogger(__name__)

OWNER = "uroboros.inline"
TOKEN_ENV = "UROBOROS_BOT_TOKEN"
INPUT_MARKER = "✍️ Значение отправлено"
UPDATES = ["inline_query", "chosen_inline_result", "callback_query"]

UNIT_TTL = 24 * 3600
MAX_UNITS = 1000
EDIT_WAIT = 5  # сколько ждать inline_message_id после отправки формы
STOP_TIMEOUT = 10
MAX_TEXT = 4096
MAX_CAPTION = 1024

STALE = "Кнопка устарела"
FOREIGN = "Эта кнопка не для вас"


class TokenRejected(InlineError):
    """Telegram не принял токен бота."""


def _new_id() -> str:
    return secrets.token_urlsafe(8)


def _title(text: str) -> str:
    plain = html.unescape(re.sub(r"<[^>]+>", "", text)).strip()
    return (plain.splitlines() or ["Uroboros"])[0][:64] or "Uroboros"


class InlineManager:
    def __init__(self, client: TelegramClient | None, db: Database):
        self.client = client
        self.db = db
        self.loader: Loader | None = None

        self.bot: Any = None  # aiogram.Bot, когда бот запущен
        self.bot_username: str | None = None
        self.bot_id: int | None = None
        self.owner_id: int | None = None
        self.error: str | None = None  # почему бот не запущен — для .inlinebot

        self._dp: Any = None
        self._task: asyncio.Task | None = None
        self._units: dict[str, Unit] = {}
        self._buttons: dict[str, tuple[Unit, dict]] = {}
        self._inputs: dict[str, tuple[Unit, dict]] = {}

    @property
    def ready(self) -> bool:
        return self.bot is not None

    @property
    def token_from_env(self) -> bool:
        return bool(os.environ.get(TOKEN_ENV))

    # --- запуск и остановка ---

    async def start(self) -> None:
        """Запускает бота. Ошибка не роняет юзербот: причина пишется в лог и в ``error``."""
        try:
            await self._start()
        except Exception as e:
            self.error = str(e) if isinstance(e, LoadError) else repr(e)
            log.warning("Inline-бот не запущен: %s", self.error)

    async def _start(self) -> None:
        if self.db.get(OWNER, "disabled"):
            self.error = "выключен командой inlinebot off"
            return
        if self.owner_id is None:
            self.owner_id = (await self.client.get_me()).id

        token = os.environ.get(TOKEN_ENV) or self.db.get(OWNER, "token")
        if token:
            try:
                await self._run(token)
                return
            except InlineError as e:
                # Сохранённый бот удалён или токен отозван — создаём новый. Токен из окружения не трогаем.
                if self.token_from_env or not isinstance(e, TokenRejected):
                    raise
                log.warning("Токен inline-бота недействителен, создаю нового бота")
        await self.create_bot()

    async def create_bot(self) -> None:
        """Создаёт нового бота через @BotFather и запускает его."""
        await self.stop()
        token = await botfather.create_bot(self.client)
        self.db.set(OWNER, "token", token)
        with contextlib.suppress(Exception):
            # Чтобы бот мог писать владельцу в личку.
            username = (await self._check_token(token)).username
            await self.client.send_message(username, "/start")
        await self._run(token)

    async def set_token(self, token: str) -> None:
        """Заменяет бота на бота с этим токеном. Неверный токен — InlineError, старый бот продолжает работать."""
        if self.token_from_env:
            raise InlineError(f"Токен задан переменной окружения {TOKEN_ENV}, сначала уберите её")
        await self._check_token(token)
        await self.stop()
        self.db.set(OWNER, "token", token)
        self.db.delete(OWNER, "disabled")
        await self._run(token)

    async def disable(self) -> None:
        await self.stop()
        self.db.set(OWNER, "disabled", True)
        self.error = "выключен командой inlinebot off"

    async def enable(self) -> None:
        self.db.delete(OWNER, "disabled")
        self.error = None
        await self._start()

    @staticmethod
    def _make_bot(token: str) -> Any:
        try:
            return Bot(token, default=DefaultBotProperties(parse_mode="HTML", link_preview_is_disabled=True))
        except Exception as e:  # aiogram проверяет формат токена при создании
            raise InlineError("Неверный формат токена бота") from e

    async def _check_token(self, token: str) -> Any:
        bot = self._make_bot(token)
        try:
            return await self._get_me(bot)
        finally:
            await bot.session.close()

    @staticmethod
    async def _get_me(bot: Any) -> Any:
        try:
            return await bot.get_me()
        except TelegramUnauthorizedError:
            raise TokenRejected("Токен бота недействителен: бот удалён или токен отозван") from None

    async def _run(self, token: str) -> None:
        bot = self._make_bot(token)
        try:
            me = await self._get_me(bot)
            if self.db.get(OWNER, "configured") != me.id:
                try:
                    await botfather.setup_inline(self.client, me.username)
                    self.db.set(OWNER, "configured", me.id)
                except InlineError as e:
                    # BotFather отказал (например, бот чужой) — не повторяем при каждом запуске.
                    self.db.set(OWNER, "configured", me.id)
                    log.warning("Не удалось настроить @%s через @BotFather: %s", me.username, e)
                except Exception as e:
                    log.warning("Не удалось настроить @%s через @BotFather: %r", me.username, e)
                me = await bot.get_me()
            if not me.supports_inline_queries:
                raise InlineError(f"У @{me.username} выключен inline-режим: включите его в @BotFather (/setinline)")
        except BaseException:
            await bot.session.close()
            raise

        dp = Dispatcher()
        dp.inline_query.register(self._on_inline_query)
        dp.chosen_inline_result.register(self._on_chosen)
        dp.callback_query.register(self._on_callback)

        self.bot, self.bot_username, self.bot_id, self._dp = bot, me.username, me.id, dp
        self.error = None
        self._task = asyncio.get_running_loop().create_task(
            dp.start_polling(bot, handle_signals=False, allowed_updates=UPDATES)
        )
        if self.client is not None:
            self.client.add_event_handler(self._on_userbot_message, events.NewMessage(outgoing=True))
        log.info("Inline-бот @%s запущен", me.username)

    async def stop(self) -> None:
        if self.client is not None:
            self.client.remove_event_handler(self._on_userbot_message)
        if self._task is not None:
            try:
                await self._dp.stop_polling()
            except RuntimeError:  # опрос ещё не начался или уже закончился
                self._task.cancel()
            await asyncio.wait({self._task}, timeout=STOP_TIMEOUT)
            if not self._task.done():
                self._task.cancel()
            elif not self._task.cancelled() and self._task.exception() is not None:
                log.error("Inline-бот завершился с ошибкой", exc_info=self._task.exception())
        if self.bot is not None:
            with contextlib.suppress(Exception):
                await self.bot.session.close()
        self.bot = self.bot_username = self.bot_id = self._dp = self._task = None
        for unit in list(self._units.values()):
            self.drop(unit)

    # --- формы ---

    def _require(self) -> None:
        if not self.ready:
            reason = f": {self.error}" if self.error else ""
            raise InlineError(f"Inline-бот не запущен{reason}")

    def new_unit(
        self,
        text: str,
        buttons: Any = None,
        *,
        stem: str | None = None,
        photo: str | None = None,
        always_allow: Any = (),
        title: str | None = None,
        description: str | None = None,
    ) -> Unit:
        limit = MAX_CAPTION if photo else MAX_TEXT
        if len(text) > limit:
            raise InlineError(f"Текст формы длиннее {limit} символов")
        if not photo and not text.strip():
            raise InlineError("Пустой текст формы")
        self._prune()
        unit = Unit(
            id=_new_id(),
            stem=stem,
            text=text,
            buttons=normalize_buttons(buttons),
            photo=photo,
            title=title,
            description=description,
            allowed=frozenset(always_allow or ()),
        )
        self._units[unit.id] = unit
        return unit

    async def form(
        self,
        message: Any,
        text: str,
        buttons: Any = None,
        *,
        stem: str | None = None,
        photo: str | None = None,
        always_allow: Any = (),
    ) -> InlineMessage:
        """Отправляет форму вместо своего сообщения ``message`` (или ответом на чужое)."""
        self._require()
        unit = self.new_unit(text, buttons, stem=stem, photo=photo, always_allow=always_allow)
        try:
            await self._send(unit, message)
        except BaseException:
            self.drop(unit)
            raise
        return InlineMessage(self, unit)

    async def _send(self, unit: Unit, message: Any) -> None:
        from telethon.errors import BotInlineDisabledError, BotResponseTimeoutError, ChatSendInlineForbiddenError

        reply_to = message.reply_to_msg_id if message.out else message.id
        try:
            results = await self.client.inline_query(self.bot_username, unit.id)
            if not results:
                raise InlineError("Inline-бот не вернул форму")
            sent = await results[0].click(message.chat_id, reply_to=reply_to)
        except ChatSendInlineForbiddenError:
            raise InlineError("В этом чате нельзя отправлять сообщения через inline-ботов") from None
        except BotInlineDisabledError:
            raise InlineError(f"У @{self.bot_username} выключен inline-режим (/setinline в @BotFather)") from None
        except BotResponseTimeoutError:
            raise InlineError("Inline-бот не ответил вовремя") from None
        unit.user_message = (sent.chat_id, sent.id)
        if message.out:
            with contextlib.suppress(Exception):
                await message.delete()

    async def list(
        self,
        message: Any,
        pages: list[str],
        *,
        buttons: Any = None,
        stem: str | None = None,
        always_allow: Any = (),
    ) -> InlineMessage:
        """Форма со страницами: ◀ и ▶ листают ``pages`` по кругу, ``buttons`` — под навигацией."""
        if not pages:
            raise InlineError("Пустой список страниц")
        extra = normalize_buttons(buttons)
        page = 0

        def view() -> tuple[str, list]:
            return pages[page], [*self._nav(page, len(pages), turn), *extra]

        async def turn(call: InlineCall, delta: int) -> None:
            nonlocal page
            page = (page + delta) % len(pages)
            await call.edit(*view())

        return await self.form(message, *view(), stem=stem, always_allow=always_allow)

    async def gallery(
        self,
        message: Any,
        photos: list[str] | Callable[[], Awaitable[str]],
        caption: str | list[str] = "",
        *,
        buttons: Any = None,
        stem: str | None = None,
        always_allow: Any = (),
    ) -> InlineMessage:
        """Галерея картинок по ссылкам: список листается ◀ ▶, функция даёт новую картинку по «Ещё».

        ``caption`` — общая подпись или список подписей к картинкам списка.
        """
        extra = normalize_buttons(buttons)

        def text_for(index: int) -> str:
            return caption[index % len(caption)] if isinstance(caption, list) and caption else str(caption or "")

        if callable(photos):
            fetch = photos

            async def more(call: InlineCall) -> None:
                await call.edit(text_for(0), [[{"text": "Ещё ▶", "callback": more}], *extra], photo=await fetch())

            first = await fetch()
            return await self.form(
                message,
                text_for(0),
                [[{"text": "Ещё ▶", "callback": more}], *extra],
                photo=first,
                stem=stem,
                always_allow=always_allow,
            )

        if not photos:
            raise InlineError("Пустой список картинок")
        index = 0

        def view() -> tuple[str, list]:
            return text_for(index), [*self._nav(index, len(photos), turn), *extra]

        async def turn(call: InlineCall, delta: int) -> None:
            nonlocal index
            index = (index + delta) % len(photos)
            await call.edit(*view(), photo=photos[index])

        return await self.form(message, *view(), photo=photos[0], stem=stem, always_allow=always_allow)

    @staticmethod
    def _nav(current: int, total: int, turn: Callable) -> list[list[dict]]:
        if total < 2:
            return []

        async def noop(call: InlineCall) -> None:
            await call.answer()

        return [
            [
                {"text": "◀", "callback": turn, "args": (-1,)},
                {"text": f"{current + 1}/{total}", "callback": noop},
                {"text": "▶", "callback": turn, "args": (1,)},
            ]
        ]

    async def edit(self, unit: Unit, text: str | None, buttons: Any = KEEP, *, photo: str | None = None) -> None:
        self._require()
        new_buttons = unit.buttons if buttons is KEEP else normalize_buttons(buttons)
        new_text = unit.text if text is None else text
        if len(new_text) > (MAX_CAPTION if photo or unit.photo else MAX_TEXT):
            raise InlineError("Текст формы слишком длинный")
        target = await self._target(unit)
        unit.text, unit.buttons = new_text, new_buttons
        markup = self._markup(unit)

        try:
            if photo is not None:
                unit.photo = photo
                media = InputMediaPhoto(media=photo, caption=unit.text or None, parse_mode="HTML")
                await self.bot.edit_message_media(media=media, reply_markup=markup, **target)
            elif unit.photo:
                await self.bot.edit_message_caption(caption=unit.text, reply_markup=markup, **target)
            else:
                await self.bot.edit_message_text(text=unit.text, reply_markup=markup, **target)
        except TelegramBadRequest as e:
            if "not modified" not in str(e):
                raise InlineError(f"Не удалось изменить форму: {e.message}") from e

    async def _target(self, unit: Unit) -> dict[str, Any]:
        if unit.inline_message_id is None and unit.bot_message is None:
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(unit.ready.wait(), EDIT_WAIT)
        if unit.inline_message_id is not None:
            return {"inline_message_id": unit.inline_message_id}
        if unit.bot_message is not None:
            return {"chat_id": unit.bot_message[0], "message_id": unit.bot_message[1]}
        raise InlineError(
            "Форму нельзя изменить до первого нажатия кнопки: у бота выключен inline feedback (/setinlinefeedback)"
        )

    async def delete(self, unit: Unit) -> None:
        self.drop(unit)
        if unit.user_message is not None and self.client is not None:
            await self.client.delete_messages(unit.user_message[0], [unit.user_message[1]])
        elif unit.bot_message is not None and self.bot is not None:
            await self.bot.delete_message(*unit.bot_message)

    def drop(self, unit: Unit) -> None:
        """Снимает кнопки формы и забывает её."""
        self._units.pop(unit.id, None)
        self._forget_keys(unit)

    def release(self, stem: str) -> None:
        """Модуль выгружен: его формы больше не отвечают на нажатия."""
        for unit in [u for u in self._units.values() if u.stem == stem]:
            self.drop(unit)

    def _forget_keys(self, unit: Unit) -> None:
        for key in unit.keys:
            self._buttons.pop(key, None)
            self._inputs.pop(key, None)
        unit.keys = []

    def _prune(self) -> None:
        deadline = time.monotonic() - UNIT_TTL
        for unit in [u for u in self._units.values() if u.created < deadline]:
            self.drop(unit)
        while len(self._units) >= MAX_UNITS:
            self.drop(next(iter(self._units.values())))

    # --- разметка ---

    def _markup(self, unit: Unit) -> Any:
        self._forget_keys(unit)
        rows = []
        for row in unit.buttons:
            line = []
            for button in row:
                text = button["text"]
                if "url" in button:
                    line.append(InlineKeyboardButton(text=text, url=button["url"]))
                elif "data" in button:
                    line.append(InlineKeyboardButton(text=text, callback_data=str(button["data"])))
                elif "input" in button:
                    key = _new_id()
                    self._inputs[key] = (unit, button)
                    unit.keys.append(key)
                    line.append(InlineKeyboardButton(text=text, switch_inline_query_current_chat=f"{key} "))
                else:
                    key = _new_id()
                    self._buttons[key] = (unit, button)
                    unit.keys.append(key)
                    line.append(InlineKeyboardButton(text=text, callback_data=key))
            rows.append(line)
        return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None

    def _result(self, unit: Unit) -> Any:
        markup = self._markup(unit)
        if unit.photo:
            return InlineQueryResultPhoto(
                id=unit.id,
                photo_url=unit.photo,
                thumbnail_url=unit.photo,
                title=unit.title,
                description=unit.description,
                caption=unit.text or None,
                parse_mode="HTML",
                reply_markup=markup,
            )
        return InlineQueryResultArticle(
            id=unit.id,
            title=unit.title or _title(unit.text),
            description=unit.description,
            input_message_content=InputTextMessageContent(message_text=unit.text, parse_mode="HTML"),
            reply_markup=markup,
        )

    # --- обновления от бота ---

    def _allowed(self, unit: Unit | None, user_id: int) -> bool:
        return user_id == self.owner_id or (unit is not None and user_id in unit.allowed)

    async def _on_inline_query(self, query: Any) -> None:
        results: list[Any] = []
        if query.from_user.id == self.owner_id:
            try:
                results = await self._inline_results(query)
            except Exception:
                log.exception("Ошибка при ответе на inline-запрос %r", query.query)
        await self.bot.answer_inline_query(query.id, results, cache_time=0, is_personal=True)

    async def _inline_results(self, query: Any) -> list[Any]:
        text = query.query.strip()
        unit = self._units.get(text)
        if unit is not None:
            return [self._result(unit)]

        key, _, rest = query.query.partition(" ")
        if key in self._inputs:
            button = self._inputs[key][1]
            value = rest.strip()
            return [
                InlineQueryResultArticle(
                    id=key,
                    title=str(button["input"]),
                    description=value or "Введите значение и выберите этот вариант",
                    input_message_content=InputTextMessageContent(message_text=INPUT_MARKER),
                )
            ]

        handlers = self.loader.inline_handlers if self.loader is not None else {}
        handler = handlers.get(key.lower())
        if handler is None:
            prefix = f"@{self.bot_username} "
            return [
                InlineQueryResultArticle(
                    id=_new_id(),
                    title=name,
                    description=h.info.doc or None,
                    input_message_content=InputTextMessageContent(
                        message_text=f"<code>{html.escape(prefix + name)}</code> {html.escape(h.info.doc)}".strip()
                    ),
                )
                for name, h in sorted(handlers.items())
                if name.startswith(key.lower())
            ][:50]

        raw = await handler.func(InlineQuery(query, rest.strip()))
        if raw is None:
            return []
        items = [raw] if isinstance(raw, dict) else list(raw)
        results = []
        for item in items[:50]:
            unit = self.new_unit(
                str(item.get("message", "")),
                item.get("buttons"),
                stem=handler.module._stem,
                photo=item.get("photo"),
                title=item.get("title"),
                description=item.get("description"),
            )
            results.append(self._result(unit))
        return results

    async def _on_chosen(self, chosen: Any) -> None:
        if chosen.from_user.id != self.owner_id:
            return
        unit = self._units.get(chosen.result_id)
        if unit is not None:
            unit.inline_message_id = chosen.inline_message_id or unit.inline_message_id
            unit.ready.set()
            return

        entry = self._inputs.get(chosen.result_id)
        if entry is None:
            return
        unit, button = entry
        value = chosen.query.partition(" ")[2].strip()
        if not value:
            return
        call = InlineCall(self, unit)
        try:
            await button["handler"](call, value, *button.get("args", ()), **button.get("kwargs", {}))
        except Exception:
            log.exception("Ошибка в обработчике ввода «%s»", button["text"])

    async def _on_callback(self, query: Any) -> None:
        data = query.data or ""
        entry = self._buttons.get(data)
        if entry is not None:
            unit, button = entry
            call = InlineCall(self, unit, query)
            if not self._allowed(unit, query.from_user.id):
                await call.answer(FOREIGN, show_alert=True)
                return
            if query.inline_message_id:
                unit.inline_message_id = query.inline_message_id
                unit.ready.set()
            await self._press(call, button)
            return

        handlers = [h for h in (self.loader.callback_handlers if self.loader else []) if h.matches(data)]
        if not handlers:
            await InlineCall(self, Unit(id="", stem=None, text="", buttons=[]), query).answer(STALE)
            return
        unit = self._unit_for_query(query, handlers[0].module._stem)
        call = InlineCall(self, unit, query)
        if not self._allowed(None, query.from_user.id):
            await call.answer(FOREIGN, show_alert=True)
            return
        for handler in handlers:
            await self._guard(call, handler.func(call), f"@callback_handler модуля {handler.module.name}")
        await call.answer()

    def _unit_for_query(self, query: Any, stem: str | None) -> Unit:
        """Сообщение, на котором нажата кнопка с ``data``: чтобы ``call.edit`` работал и здесь."""
        for unit in self._units.values():
            if query.inline_message_id and unit.inline_message_id == query.inline_message_id:
                return unit
        message = getattr(query, "message", None)
        unit = Unit(
            id=_new_id(),
            stem=stem,
            text=getattr(message, "html_text", None) or "",
            buttons=[],
            inline_message_id=query.inline_message_id,
            bot_message=(message.chat.id, message.message_id) if message is not None else None,
        )
        self._units[unit.id] = unit
        return unit

    async def _press(self, call: InlineCall, button: dict) -> None:
        if button.get("action") == "close":
            await self._guard(call, call.delete(), "закрытии формы")
        elif button.get("confirm"):
            await self._guard(call, self._ask_confirm(call, button), "подтверждении")
        else:
            callback = button["callback"]
            coro = callback(call, *button.get("args", ()), **button.get("kwargs", {}))
            await self._guard(call, coro, f"кнопке «{button['text']}»")
        await call.answer()

    async def _ask_confirm(self, call: InlineCall, button: dict) -> None:
        """Кнопка с ``confirm``: сначала вопрос «Да / Отмена», потом её ``callback``."""
        unit = call.unit
        saved_text, saved_buttons = unit.text, unit.buttons
        question = button["confirm"] if isinstance(button["confirm"], str) else "Вы уверены?"
        original = {k: v for k, v in button.items() if k != "confirm"}

        async def yes(call: InlineCall) -> None:
            unit.text, unit.buttons = saved_text, saved_buttons
            callback = original["callback"]
            await callback(call, *original.get("args", ()), **original.get("kwargs", {}))
            if not call.edited and call.unit.id in self._units:
                await call.edit(saved_text, saved_buttons)

        async def no(call: InlineCall) -> None:
            await call.edit(saved_text, saved_buttons)

        await call.edit(question, [[{"text": "✅ Да", "callback": yes}, {"text": "Отмена", "callback": no}]])

    async def _guard(self, call: InlineCall, coro: Awaitable[Any], where: str) -> None:
        try:
            await coro
        except LoadError as e:
            await call.answer(str(e)[:200], show_alert=True)
        except Exception:
            log.exception("Ошибка в %s", where)
            await call.answer("Ошибка, подробности в логах (.logs)", show_alert=True)

    async def _on_userbot_message(self, event: Any) -> None:
        """Удаляет служебное сообщение, которое уходит в чат при вводе текста в форму."""
        message = event.message
        if self.bot_id is not None and message.via_bot_id == self.bot_id and message.raw_text == INPUT_MARKER:
            with contextlib.suppress(Exception):
                await message.delete()
