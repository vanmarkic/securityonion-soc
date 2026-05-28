"""GridMembersService — business logic for grid member endpoints."""

from __future__ import annotations

import logging

from src.domain.config import is_valid_minion_id
from src.domain.gridmember import GridMember
from src.ports.auth import Authorizer, Unauthorized
from src.ports.gridmembers import GridMembersstore

logger = logging.getLogger(__name__)

VALID_OPERATIONS = frozenset({"add", "reject", "delete", "test", "restart"})

# PCAP magic bytes (big-endian and little-endian variants)
_PCAP_MAGICS = [
    bytes([0xD4, 0xC3, 0xB2, 0xA1]),
    bytes([0xA1, 0xB2, 0xC3, 0xD4]),
    bytes([0xA1, 0xB2, 0x3C, 0x4D]),
    bytes([0x4D, 0x3C, 0xB2, 0xA1]),
    bytes([0xC3, 0xD4, 0xA1, 0xB2]),
]

# EVTX magic bytes: "ElfFile"
_EVTX_MAGIC = bytes([0x45, 0x6C, 0x66, 0x46, 0x69, 0x6C, 0x65])


class GridMembersService:
    """Service layer for grid member operations."""

    def __init__(
        self,
        gridmembersstore: GridMembersstore,
        authorizer: Authorizer,
    ) -> None:
        self._store = gridmembersstore
        self._authorizer = authorizer

    async def get_members(self) -> list[GridMember]:
        """Retrieve all grid members."""
        return await self._store.get_members()

    async def manage_member(self, operation: str, member_id: str) -> None:
        """Perform an operation on a grid member."""
        if not is_valid_minion_id(member_id):
            raise ValueError("Invalid minion ID")
        if operation not in VALID_OPERATIONS:
            raise ValueError("Invalid operation")
        await self._store.manage_member(operation, member_id)

    async def check_import_auth(self, user_id: str, node_id: str) -> None:
        """Verify that the user is authorized to import data.

        Raises Unauthorized if not allowed.
        """
        if not is_valid_minion_id(node_id):
            raise ValueError("Invalid minion ID")
        await self._authorizer.check_authorized(user_id, "write", "events")
