"""``from ..inline.types import InlineCall, InlineQuery, ...`` — для аннотаций и isinstance."""

from ..inline_adapter import HikkaCall as InlineCall
from ..inline_adapter import HikkaInlineMessage as InlineMessage
from ..inline_adapter import HikkaInlineQuery as InlineQuery

BotInlineCall = InlineCall
BotInlineMessage = InlineMessage


class InlineUnit:
    """Заглушка типа Hikka: в Uroboros формы не наследуются от него."""


class BotMessage:
    """Заглушка типа Hikka для сообщений бота."""


__all__ = [
    "BotInlineCall",
    "BotInlineMessage",
    "BotMessage",
    "InlineCall",
    "InlineMessage",
    "InlineQuery",
    "InlineUnit",
]
