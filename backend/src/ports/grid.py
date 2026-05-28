"""Grid ports — defines contracts for node data and status retrieval."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.domain.node import Node
from src.domain.status import Status


@runtime_checkable
class Datastore(Protocol):
    """Protocol for retrieving grid node data."""

    async def get_nodes(self) -> list[Node]: ...


@runtime_checkable
class Statusstore(Protocol):
    """Protocol for retrieving grid status summary."""

    async def get_status_summary(self) -> Status: ...
