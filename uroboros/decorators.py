"""Декораторы для методов модуля: команды, вотчеры, обработчики inline-бота."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

COMMAND_ATTR = "_uroboros_command"
WATCHER_ATTR = "_uroboros_watcher"
INLINE_ATTR = "_uroboros_inline"
CALLBACK_ATTR = "_uroboros_callback"


@dataclass(frozen=True)
class CommandInfo:
    name: str
    aliases: tuple[str, ...]
    doc: str
    only_pm: bool = False
    only_groups: bool = False
    only_channels: bool = False
    chats: frozenset[int] | None = None
    only_reply: bool = False
    no_reply: bool = False
    filter: Callable[[Any], bool] | None = None

    def restrictions(self) -> list[str]:
        """Ограничения команды словами — для .help."""
        result = []
        if self.only_pm:
            result.append("только в личных сообщениях")
        if self.only_groups:
            result.append("только в группах")
        if self.only_channels:
            result.append("только в каналах")
        if self.chats is not None:
            result.append("только в выбранных чатах")
        if self.only_reply:
            result.append("ответом на сообщение")
        if self.no_reply:
            result.append("не ответом на сообщение")
        return result

    def rejection(self, message: Any) -> str | None:
        """Почему команду нельзя выполнить для этого сообщения; None — можно."""
        if self.only_pm and not message.is_private:
            return "Команда работает только в личных сообщениях"
        if self.only_groups and not message.is_group:
            return "Команда работает только в группах"
        if self.only_channels and not (message.is_channel and not message.is_group):
            return "Команда работает только в каналах"
        if self.chats is not None and message.chat_id not in self.chats:
            return "Команда недоступна в этом чате"
        if self.only_reply and not message.is_reply:
            return "Команду нужно отправить ответом на сообщение"
        if self.no_reply and message.is_reply:
            return "Команду нельзя отправлять ответом на сообщение"
        if self.filter is not None and not self.filter(message):
            return "Команда недоступна для этого сообщения"
        return None


@dataclass(frozen=True)
class WatcherInfo:
    only_outgoing: bool
    only_incoming: bool
    filter: Callable[[Any], bool] | None


def command(
    name: str | None = None,
    *,
    aliases: list[str] | tuple[str, ...] = (),
    doc: str | None = None,
    only_pm: bool = False,
    only_groups: bool = False,
    only_channels: bool = False,
    chats: list[int] | tuple[int, ...] | None = None,
    only_reply: bool = False,
    no_reply: bool = False,
    filter: Callable[[Any], bool] | None = None,
):
    """Помечает метод как команду ``<префикс><name>``.

    Без имени берётся имя метода (суффикс ``cmd`` отбрасывается).
    Описание — ``doc`` или докстринг метода.

    Фильтры ограничивают, где команда работает: ``only_pm``, ``only_groups``,
    ``only_channels``, ``chats`` (список id чатов), ``only_reply``, ``no_reply`` и
    произвольный ``filter(message) -> bool``. Если сообщение не подходит, пользователь
    получает ответ с причиной, а команда не вызывается.
    """
    if sum((only_pm, only_groups, only_channels)) > 1:
        raise ValueError("only_pm, only_groups и only_channels взаимоисключающие")
    if only_reply and no_reply:
        raise ValueError("only_reply и no_reply взаимоисключающие")

    def decorator(func):
        cmd_name = (name or func.__name__.removesuffix("cmd")).lower()
        setattr(
            func,
            COMMAND_ATTR,
            CommandInfo(
                name=cmd_name,
                aliases=tuple(alias.lower() for alias in aliases),
                doc=(doc or func.__doc__ or "").strip(),
                only_pm=only_pm,
                only_groups=only_groups,
                only_channels=only_channels,
                chats=frozenset(chats) if chats is not None else None,
                only_reply=only_reply,
                no_reply=no_reply,
                filter=filter,
            ),
        )
        return func

    return decorator


def watcher(
    *,
    only_outgoing: bool = False,
    only_incoming: bool = False,
    filter: Callable[[Any], bool] | None = None,
):
    """Помечает метод как обработчик всех новых сообщений."""

    def decorator(func):
        setattr(func, WATCHER_ATTR, WatcherInfo(only_outgoing, only_incoming, filter))
        return func

    return decorator


@dataclass(frozen=True)
class InlineHandlerInfo:
    name: str
    doc: str


@dataclass(frozen=True)
class CallbackHandlerInfo:
    prefix: str | None


def inline_handler(name: str | None = None, *, doc: str | None = None):
    """Помечает метод как обработчик inline-запроса ``@бот <name> аргументы``.

    Без имени берётся имя метода (суффикс ``_inline_handler`` отбрасывается).
    Метод получает ``InlineQuery`` (``query.args`` — текст после имени) и возвращает
    результат или список результатов: словари с ``title``, ``description``, ``message``
    (HTML), ``buttons`` и ``photo``. Отвечает бот только владельцу аккаунта.
    """

    def decorator(func):
        handler_name = (name or func.__name__.removesuffix("_inline_handler")).lower()
        if not handler_name or any(ch.isspace() for ch in handler_name):
            raise ValueError("Имя inline-обработчика — одно слово")
        setattr(func, INLINE_ATTR, InlineHandlerInfo(handler_name, (doc or func.__doc__ or "").strip()))
        return func

    return decorator


def callback_handler(prefix: str | None = None):
    """Помечает метод как обработчик нажатий кнопок с ``"data"`` (и кнопок в сообщениях бота).

    ``prefix`` — только для ``data``, которые с него начинаются. Метод получает ``InlineCall``,
    ``call.data`` — данные кнопки. Нажатия принимаются только от владельца аккаунта.
    """

    def decorator(func):
        setattr(func, CALLBACK_ATTR, CallbackHandlerInfo(prefix))
        return func

    return decorator
