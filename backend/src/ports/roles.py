"""Rolestore port — defines the contract for role persistence."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Rolestore(Protocol):
    """Protocol that any role-storing adapter must satisfy."""

    async def get_roles(self) -> list[str]: ...

    async def get_permissions(self) -> dict[str, list[str]]: ...

    async def ensure_default_role_for_user(self) -> None: ...
