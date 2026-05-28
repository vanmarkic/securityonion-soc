"""Clientstore and AdminClientstore ports — contracts for client persistence."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.domain.client import Client


@runtime_checkable
class Clientstore(Protocol):
    """Protocol for client reads. Ported from Go Clientstore."""

    async def get_clients(self) -> list[Client]: ...

    async def get_client_by_id(self, client_id: str) -> Client | None: ...


@runtime_checkable
class AdminClientstore(Protocol):
    """Protocol for client administration (writes). Ported from Go AdminClientstore."""

    async def add_client(self, client: Client) -> Client: ...

    async def delete_client(self, client_id: str) -> None: ...

    async def generate_secret(self, client_id: str) -> Client: ...

    async def update_client(self, client: Client) -> None: ...

    async def add_client_permission(self, client_id: str, permission: str) -> None: ...

    async def delete_client_permission(self, client_id: str, permission: str) -> None: ...
