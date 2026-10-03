"""Декораторы прав Hikka (``@loader.owner`` и т.п.) поверх уровней доступа Uroboros.

Групповые права Hikka (админы чата, участники) Uroboros не поддерживает: такие команды
доступны только владельцам.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

ACCESS_ATTR = "_hikka_access"

# Битовые флаги Hikka — для модулей, которые на них ссылаются.
OWNER = 1 << 0
GROUP_OWNER = 1 << 2
GROUP_ADMIN_ADD_ADMINS = 1 << 3
GROUP_ADMIN_CHANGE_INFO = 1 << 4
GROUP_ADMIN_BAN_USERS = 1 << 5
GROUP_ADMIN_DELETE_MESSAGES = 1 << 6
GROUP_ADMIN_PIN_MESSAGES = 1 << 7
GROUP_ADMIN_INVITE_USERS = 1 << 8
GROUP_ADMIN = 1 << 9
GROUP_MEMBER = 1 << 10
PM = 1 << 11
EVERYONE = 1 << 12
SUDO = 1 << 13
SUPPORT = 1 << 14
DEFAULT_PERMISSIONS = OWNER


def _access(level: str) -> Callable[[Any], Any]:
    def decorator(func: Any) -> Any:
        setattr(func, ACCESS_ATTR, level)
        return func

    return decorator


owner = _access("owner")
sudo = _access("sudo")
support = _access("support")
unrestricted = _access("everyone")
inline_everyone = unrestricted

# Не поддерживаются: только владельцам.
group_owner = _access("owner")
group_admin = _access("owner")
group_admin_add_admins = _access("owner")
group_admin_change_info = _access("owner")
group_admin_ban_users = _access("owner")
group_admin_delete_messages = _access("owner")
group_admin_pin_messages = _access("owner")
group_admin_invite_users = _access("owner")
group_member = _access("owner")
pm = _access("owner")


def access_of(func: Any) -> str:
    """Уровень Uroboros для команды Hikka. По умолчанию, как в Hikka, — только владельцу."""
    return getattr(func, ACCESS_ATTR, "owner")
