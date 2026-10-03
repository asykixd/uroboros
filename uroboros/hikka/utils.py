"""``utils`` Hikka поверх ``uroboros.utils``.

Поведение функций повторяет Hikka (AGPL-3.0, https://github.com/hikariatama/Hikka).
Функции, которых здесь нет, при обращении дают понятную ошибку.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import html
import json
import os
import random
import re
import shlex
import string
import subprocess
import time
import urllib.parse
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from telethon import utils as tl_utils

from .. import __version__
from .. import utils as core

escape_html = core.escape_html
run_sync = core.run_sync
quote = core.quote

_FACES = [
    "ヽ(๏∀˙ )ノ",
    "ヽ(๏∀๏ )ﾉ",
    "(◕‿◕✿)",
    "(｡◕‿◕｡)",
    "ʕ•ᴥ•ʔ",
    "(づ｡◕‿‿◕｡)づ",
    "(ﾉ◕ヮ◕)ﾉ*:･ﾟ✧",
    "¯\\_(ツ)_/¯",
]


def get_args(message: Any) -> list[str]:
    """Аргументы команды списком (с учётом кавычек)."""
    return core.get_args(message)


def get_args_raw(message: Any) -> str:
    return core.get_args_raw(message)


def get_args_html(message: Any) -> str:
    """Аргументы команды с HTML-разметкой."""
    text = getattr(message, "text", None) or ""
    parts = text.split(maxsplit=1)
    return parts[1] if len(parts) > 1 else ""


def get_args_split_by(message: Any, separator: str) -> list[str]:
    return [part.strip() for part in get_args_raw(message).split(separator) if part.strip()]


def get_chat_id(message: Any) -> int:
    """Id чата без ``-100`` (как в Hikka)."""
    return tl_utils.resolve_id(message.chat_id)[0]


def get_display_name(entity: Any) -> str:
    return tl_utils.get_display_name(entity)


def register_placeholder(*args: Any, **kwargs: Any) -> None:
    """Плейсхолдеры для .info из Hikka: в Uroboros их нет, регистрация ничего не делает."""


def get_entity_id(entity: Any) -> int:
    return tl_utils.get_peer_id(entity)


def escape_quotes(text: str) -> str:
    return escape_html(text).replace('"', "&quot;")


def get_base_dir() -> str:
    return str(Path(__file__).resolve().parent)


def get_dir(mod: str) -> str:
    return os.path.abspath(os.path.dirname(os.path.abspath(mod)))


async def get_user(message: Any) -> Any:
    return await core.get_user(message)


def run_async(loop: asyncio.AbstractEventLoop, coro: Any) -> Any:
    return asyncio.run_coroutine_threadsafe(coro, loop).result()


def censor(obj: Any, *args: Any, **kwargs: Any) -> Any:
    return obj


def relocate_entities(entities: list | None, offset: int, text: str | None = None) -> list:
    length = len(text) if text is not None else 0
    for ent in entities or []:
        ent.offset += offset
        if ent.offset < 0:
            ent.length += ent.offset
            ent.offset = 0
        if text is not None and ent.offset + ent.length > length:
            ent.length = length - ent.offset
    return entities or []


async def answer_file(message: Any, file: Any, caption: str | None = None, **kwargs: Any) -> Any:
    return await core.answer_file(message, file, caption, **kwargs)


async def answer(message: Any, response: Any, *, reply_markup: Any = None, **kwargs: Any) -> Any:
    """Ответ на команду. С ``reply_markup`` — inline-форма, с ``file`` — файл."""
    if reply_markup is not None:
        from .state import get_loader

        inline = get_loader().inline
        if inline is not None and inline.ready:
            from .inline_adapter import HikkaInlineMessage, convert_markup

            with contextlib.suppress(Exception):
                return HikkaInlineMessage(await inline.form(message, str(response), convert_markup(reply_markup)))
    file = kwargs.pop("file", None)
    if file is not None:
        return await core.answer_file(message, file, caption=str(response) if response else None, **kwargs)
    kwargs.pop("asfile", None)
    return await core.answer(message, str(response), **kwargs)


async def get_target(message: Any, arg_no: int = 0) -> int | None:
    """Id пользователя, о котором команда: ответ, аргумент номер ``arg_no`` или собеседник в личке."""
    args = get_args(message)
    arg = args[arg_no] if len(args) > arg_no else None
    if arg is None and not message.is_reply and not message.is_private:
        return None
    entity = await core.get_target(message, arg if arg is not None else None)
    return None if entity is None else get_entity_id(entity)


def merge(a: dict, b: dict) -> dict:
    """Рекурсивно сливает словарь ``a`` в ``b``."""
    for key in a:
        if key in b and isinstance(a[key], dict) and isinstance(b[key], dict):
            b[key] = merge(a[key], b[key])
        elif key in b and isinstance(a[key], list) and isinstance(b[key], list):
            b[key] = list(dict.fromkeys(b[key] + a[key]))
        else:
            b[key] = a[key]
    return b


def get_link(user: Any) -> str:
    """Ссылка на пользователя или чат."""
    username = getattr(user, "username", None)
    if getattr(user, "first_name", None) is not None or not username:
        return f"tg://user?id={user.id}"
    return f"https://t.me/{username}"


def get_entity_url(entity: Any, openmessage: bool = False) -> str:
    username = getattr(entity, "username", None)
    if username:
        return f"https://t.me/{username}"
    if getattr(entity, "first_name", None) is not None:
        return f"tg://openmessage?user_id={entity.id}" if openmessage else f"tg://user?id={entity.id}"
    return f"https://t.me/c/{entity.id}"


async def get_message_link(message: Any, chat: Any = None) -> str:
    chat = chat or await message.get_chat()
    username = getattr(chat, "username", None)
    if username:
        return f"https://t.me/{username}/{message.id}"
    return f"https://t.me/c/{tl_utils.resolve_id(message.chat_id)[0]}/{message.id}"


def chunks(_list: list | str, n: int) -> list:
    return [_list[i : i + n] for i in range(0, len(_list), n)]


def get_named_platform() -> str:
    if "com.termux" in os.environ.get("PREFIX", ""):
        return "📱 Termux"
    if os.environ.get("DOCKER"):
        return "🐳 Docker"
    return "🐍 Uroboros"


def get_platform_emoji() -> str:
    return "🐍"


def uptime() -> int:
    return int(time.time() - core.START_TIME)


def formatted_uptime() -> str:
    return core.format_duration(uptime())


def ascii_face() -> str:
    return escape_html(random.choice(_FACES))


def array_sum(array: list) -> list:
    result = []
    for item in array:
        result += item
    return result


def rand(size: int, /) -> str:
    return "".join(random.choice(string.ascii_letters + string.digits) for _ in range(size))


def smart_split(text: str, entities: Any = None, length: int = 4096, split_on=("\n", " "), min_length: int = 1):
    """Делит длинный текст на части не длиннее ``length``, по возможности по переводам строк."""
    text = text or ""
    while len(text) > length:
        cut = -1
        for sep in split_on:
            cut = text.rfind(sep, min_length, length)
            if cut != -1:
                break
        if cut == -1:
            cut = length
        yield text[:cut]
        text = text[cut:].lstrip("\n")
    if text:
        yield text


def check_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return False
    return bool(parsed.scheme and parsed.netloc)


def _git(*args: str) -> str:
    root = Path(core.__file__).resolve().parent.parent
    try:
        return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return ""


def get_git_hash() -> str | bool:
    return _git("rev-parse", "HEAD") or False


def get_commit_url() -> str:
    commit = get_git_hash()
    return f'<a href="https://github.com/asykixd/uroboros/commit/{commit}">#{str(commit)[:7]}</a>' if commit else ""


def get_git_info() -> tuple[str, str]:
    commit = get_git_hash()
    return (commit or "", f"https://github.com/asykixd/uroboros/commit/{commit}" if commit else "")


def get_version_raw() -> str:
    return __version__


def is_serializable(x: Any, /) -> bool:
    try:
        json.dumps(x)
    except Exception:
        return False
    return True


def get_lang_flag(countrycode: str) -> str:
    code = [c for c in countrycode.lower() if c in string.ascii_letters]
    if len(code) == 2:
        return "".join(chr(ord(c.upper()) + (ord("🇦") - ord("A"))) for c in code)
    return countrycode


def remove_html(text: str, escape: bool = False, keep_emojis: bool = False) -> str:
    plain = html.unescape(re.sub(r"<[^>]+>", "", text or ""))
    return escape_html(plain) if escape else plain


def mime_type(message: Any) -> str:
    file = getattr(message, "file", None)
    return getattr(file, "mime_type", None) or ""


def validate_html(text: str) -> str:
    return text


def iter_attrs(obj: Any, /) -> Iterator[tuple[str, Any]]:
    return ((attr, getattr(obj, attr)) for attr in dir(obj) if not attr.startswith("_"))


def atexit(func: Callable, use_signal: Any = None, *args: Any, **kwargs: Any) -> None:
    import atexit as _atexit

    _atexit.register(functools.partial(func, *args, **kwargs))


def get_topic(message: Any) -> int | None:
    reply = getattr(message, "reply_to", None)
    if reply is not None and getattr(reply, "forum_topic", False):
        return reply.reply_to_top_id or reply.reply_to_msg_id
    return None


def get_ram_usage() -> float:
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(usage / (1024 * 1024 if os.uname().sysname == "Darwin" else 1024), 1)
    except Exception:
        return 0.0


def get_cpu_usage() -> float:
    return 0.0


def get_kwargs() -> dict:
    return {}


def split_args(text: str) -> list[str]:
    try:
        return shlex.split(text)
    except ValueError:
        return text.split()


# --- служебные чаты модулей (как в Hikka) ---

_FLOOD_PAUSE = 0.5  # пауза между запросами создания чата, как fw_protect в Hikka
_channels: dict[str, Any] = {}  # название → чат: asset_channel не ищет его в диалогах каждый раз


async def _pause() -> None:
    await asyncio.sleep(_FLOOD_PAUSE)


def _bot_username() -> str | None:
    from .state import get_loader

    inline = get_loader().inline
    return inline.bot_username if inline is not None else None


async def invite_inline_bot(client: Any, peer: Any) -> None:
    """Добавляет inline-бота в чат и даёт ему право банить (нужно модулям для кнопок в чате)."""
    from telethon.tl.functions.channels import EditAdminRequest, InviteToChannelRequest
    from telethon.tl.types import ChatAdminRights

    bot = _bot_username()
    if bot is None:
        raise RuntimeError("Inline-бот не запущен, пригласить его в чат нельзя")
    try:
        await client(InviteToChannelRequest(peer, [bot]))
    except Exception as e:
        raise RuntimeError("Не удалось пригласить inline-бота в служебный чат модуля") from e
    with contextlib.suppress(Exception):
        await client(
            EditAdminRequest(channel=peer, user_id=bot, admin_rights=ChatAdminRights(ban_users=True), rank="Uroboros")
        )


async def dnd(client: Any, peer: Any, archive: bool = True) -> bool:
    """Отключает уведомления чата и, если ``archive``, убирает его в архив."""
    from telethon.tl.functions.account import UpdateNotifySettingsRequest
    from telethon.tl.types import InputPeerNotifySettings

    try:
        await client(
            UpdateNotifySettingsRequest(
                peer=peer,
                settings=InputPeerNotifySettings(show_previews=False, silent=True, mute_until=2**31 - 1),
            )
        )
        if archive:
            await _pause()
            await client.edit_folder(peer, 1)
    except Exception:
        import logging

        logging.getLogger(__name__).exception("utils.dnd: не удалось")
        return False
    return True


async def set_avatar(client: Any, peer: Any, avatar: str | bytes) -> bool:
    """Ставит аватарку чату: ссылка на картинку или байты."""
    from telethon.tl.functions.channels import EditPhotoRequest

    if isinstance(avatar, str) and check_url(avatar):
        import urllib.request

        def fetch() -> bytes:
            request = urllib.request.Request(avatar, headers={"User-Agent": "Uroboros"})
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read(10 * 1024 * 1024)

        data = await run_sync(fetch)
    elif isinstance(avatar, bytes):
        data = avatar
    else:
        return False
    await _pause()
    await client(EditPhotoRequest(channel=peer, photo=await client.upload_file(data, file_name="photo.png")))
    return True


async def asset_channel(
    client: Any,
    title: str,
    description: str,
    *,
    channel: bool = False,
    silent: bool = False,
    archive: bool = False,
    invite_bot: bool = False,
    avatar: str | None = None,
    ttl: int | None = None,
    _folder: str | None = None,
) -> tuple[Any, bool]:
    """Находит служебный чат модуля по названию или создаёт его. Возвращает (чат, создан ли сейчас).

    ``channel`` — канал, иначе супергруппа; ``silent`` — без уведомлений; ``archive`` — в архив;
    ``invite_bot`` — добавить inline-бота; ``ttl`` — автоудаление сообщений.
    """
    from telethon.tl.functions.channels import CreateChannelRequest
    from telethon.tl.functions.messages import SetHistoryTTLRequest

    if title in _channels:
        return _channels[title], False

    async for dialog in client.iter_dialogs():
        if dialog.title == title and getattr(dialog.entity, "creator", False):
            _channels[title] = dialog.entity
            if invite_bot:
                bot_id = None
                from .state import get_loader

                inline = get_loader().inline
                bot_id = inline.bot_id if inline is not None else None
                participants = await client.get_participants(dialog.entity, limit=100)
                if bot_id is not None and all(p.id != bot_id for p in participants):
                    await _pause()
                    await invite_inline_bot(client, dialog.entity)
            return dialog.entity, False

    await _pause()
    peer = (await client(CreateChannelRequest(title, description, megagroup=not channel))).chats[0]
    if invite_bot:
        await _pause()
        await invite_inline_bot(client, peer)
    if silent:
        await _pause()
        await dnd(client, peer, archive)
    elif archive:
        await _pause()
        await client.edit_folder(peer, 1)
    if avatar:
        await _pause()
        with contextlib.suppress(Exception):
            await set_avatar(client, peer, avatar)
    if ttl:
        await _pause()
        await client(SetHistoryTTLRequest(peer=peer, period=ttl))
    _channels[title] = peer
    return peer, True


_UNSUPPORTED = {
    "find_caller": "поиск вызывающего модуля",
    "asset_forum_topic": "служебные темы форума (есть только в форке Heroku)",
}


def __getattr__(name: str) -> Any:
    what = _UNSUPPORTED.get(name)
    detail = f" ({what})" if what else ""
    raise AttributeError(f"utils.{name} из Hikka не поддерживается Uroboros{detail}")
