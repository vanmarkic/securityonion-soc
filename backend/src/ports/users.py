"""Userstore and AdminUserstore ports — contracts for user persistence."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.domain.user import User


@runtime_checkable
class Userstore(Protocol):
    """Protocol that any user-storing adapter must satisfy (read-only)."""

    async def get_users(self) -> list[User]: ...

    async def get_user_by_id(self, user_id: str) -> User | None: ...


@runtime_checkable
class AdminUserstore(Protocol):
    """Protocol for user administration (writes). Ported from Go AdminUserstore."""

    async def add_user(self, user: User) -> None: ...

    async def delete_user(self, user_id: str) -> None: ...

    async def update_profile(self, user: User) -> None: ...

    async def reset_password(self, user_id: str, password: str) -> None: ...

    async def enable_user(self, user_id: str) -> None: ...

    async def disable_user(self, user_id: str) -> None: ...

    async def add_role(self, user_id: str, role: str, bypass_auth_check: bool = False) -> None: ...

    async def delete_role(self, user_id: str, role: str) -> None: ...

    async def sync_users(self) -> None: ...
