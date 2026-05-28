"""RolesService -- business logic ported from Go roleshandler.go."""

from __future__ import annotations

from src.ports.roles import Rolestore


class RolesService:
    """Business logic for role and permission queries."""

    def __init__(self, rolestore: Rolestore) -> None:
        self._rolestore = rolestore

    async def get_roles(self) -> list[str]:
        return await self._rolestore.get_roles()

    async def get_permissions(self) -> dict[str, list[str]]:
        return await self._rolestore.get_permissions()
