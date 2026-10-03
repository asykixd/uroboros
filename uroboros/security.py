"""Группы доступа и права на команды.

Уровни от строгого к открытому: ``owner`` (аккаунт юзербота и добавленные владельцы),
``sudo``, ``support``, ``everyone``. Команде нужен уровень не ниже заданного: команду
уровня ``support`` могут выполнять support, sudo и владельцы. Свои исходящие сообщения —
всегда уровень ``owner``; входящие команды выполняются, только если отправитель в группе
с нужным уровнем (или команде явно выдан ``everyone``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .database import Database
    from .loader import Command

SECURITY_OWNER = "uroboros.security"
LEVELS = ("owner", "sudo", "support", "everyone")
GROUPS = ("owner", "sudo", "support")
DEFAULT_LEVEL = "sudo"

LEVEL_NAMES = {
    "owner": "владельцы",
    "sudo": "sudo",
    "support": "support",
    "everyone": "все",
}


class Security:
    def __init__(self, db: Database):
        self.db = db
        self.me_id: int | None = None  # аккаунт юзербота, проставляется после входа

    # --- группы ---

    def members(self, group: str) -> list[int]:
        if group not in GROUPS:
            raise ValueError(group)
        return self.db.get(SECURITY_OWNER, group, [])

    def add(self, group: str, user_id: int) -> bool:
        """Добавляет в группу и убирает из остальных. False — уже был в ней."""
        if user_id in self.members(group):
            return False
        for other in GROUPS:
            if other != group:
                self.remove(other, user_id)
        self.db.set(SECURITY_OWNER, group, [*self.members(group), user_id])
        return True

    def remove(self, group: str, user_id: int) -> bool:
        members = self.members(group)
        if user_id not in members:
            return False
        self.db.set(SECURITY_OWNER, group, [m for m in members if m != user_id])
        return True

    def level_of(self, user_id: int | None) -> str:
        if user_id is not None and (user_id == self.me_id or user_id in self.members("owner")):
            return "owner"
        for group in ("sudo", "support"):
            if user_id in self.members(group):
                return group
        return "everyone"

    def is_owner(self, user_id: int | None) -> bool:
        return self.level_of(user_id) == "owner"

    # --- права на команды ---

    def overrides(self) -> dict[str, str]:
        """Уровни, заданные пользователем через ``.security``: команда → уровень."""
        return self.db.get(SECURITY_OWNER, "commands", {})

    def required(self, command: Command) -> str:
        return self.overrides().get(command.name, command.info.access)

    def set_required(self, name: str, level: str | None) -> None:
        """``None`` — вернуть уровень по умолчанию из ``@command``."""
        overrides = self.overrides()
        if level is None:
            overrides.pop(name, None)
        else:
            if level not in LEVELS:
                raise ValueError(level)
            overrides[name] = level
        self.db.set(SECURITY_OWNER, "commands", overrides)

    def allows(self, level: str, user_id: int | None) -> bool:
        return LEVELS.index(self.level_of(user_id)) <= LEVELS.index(level)

    def can_run(self, command: Command, user_id: int | None) -> bool:
        return self.allows(self.required(command), user_id)
