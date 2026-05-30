"""SaltGridMembersstore — grid member management over the Salt relay.

Ported from server/modules/salt/saltstore.go (GetMembers + ManageMember).
Authorization (Go's CheckAuthorized calls) is handled by the service/route
layer in this hexagonal codebase, not by the adapter.
"""

from __future__ import annotations

import uuid
from itertools import count

from src.adapters.salt.members import parse_members
from src.adapters.salt.relay import SaltRelayClient
from src.domain.gridmember import GridMember

# Go raises errors.New("ERROR_SALT_MANAGE_MEMBER") when the relay returns the
# literal "false" for either command.
ERROR_SALT_MANAGE_MEMBER = "ERROR_SALT_MANAGE_MEMBER"


class SaltManageMemberError(Exception):
    """Raised when the relay rejects a grid-member command (output == "false")."""

    def __init__(self, message: str = ERROR_SALT_MANAGE_MEMBER) -> None:
        super().__init__(message)


class SaltGridMembersstore:
    """Manage grid members by relaying list-minions / manage-minion commands.

    Go builds ``command_id = "<requestId>_<command>"``. No request context is
    plumbed into the adapter yet, so we accept an optional ``request_id`` (the
    route/service layer will supply a real one later) and fall back to a random
    per-instance prefix. A per-call counter is appended so concurrent commands
    sharing a prefix never collide on the relay's file-queue keys.
    """

    def __init__(self, relay: SaltRelayClient, request_id: str | None = None) -> None:
        self._relay = relay
        self._request_id = request_id or uuid.uuid4().hex
        self._counter = count()

    def _command_id(self, command: str) -> str:
        suffix = next(self._counter)
        if suffix == 0:
            return f"{self._request_id}_{command}"
        return f"{self._request_id}-{suffix}_{command}"

    async def get_members(self) -> list[GridMember]:
        output = await self._relay.exec_command(
            self._command_id("list-minions"), {"command": "list-minions"}
        )
        if output == "false":
            raise SaltManageMemberError
        return parse_members(output)

    async def manage_member(self, operation: str, member_id: str) -> None:
        output = await self._relay.exec_command(
            self._command_id("manage-minion"),
            {"command": "manage-minion", "operation": operation, "id": member_id},
        )
        if output == "false":
            raise SaltManageMemberError
