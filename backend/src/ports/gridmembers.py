"""GridMembersstore port — defines the contract for grid member management."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.domain.gridmember import GridMember


@runtime_checkable
class GridMembersstore(Protocol):
    """Protocol that any grid-member-managing adapter must satisfy."""

    async def get_members(self) -> list[GridMember]: ...

    async def manage_member(self, operation: str, member_id: str) -> None: ...
