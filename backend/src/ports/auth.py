"""Authorization port — defines the contract for RBAC checks."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class Unauthorized(Exception):
    """Raised when a user is not authorized for an operation on a resource."""

    def __init__(self, user_id: str, operation: str, resource: str) -> None:
        self.user_id = user_id
        self.operation = operation
        self.resource = resource
        super().__init__(f"User {user_id} not authorized for {operation} on {resource}")


@runtime_checkable
class Authorizer(Protocol):
    """Protocol that any authorization adapter must satisfy."""

    async def check_authorized(self, user_id: str, operation: str, resource: str) -> None: ...
