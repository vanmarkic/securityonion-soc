"""Userstore port — defines the contract for user persistence."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.domain.user import User


@runtime_checkable
class Userstore(Protocol):
    """Protocol that any user-storing adapter must satisfy."""

    async def get_users(self) -> list[User]: ...

    async def get_user_by_id(self, user_id: str) -> User | None: ...
