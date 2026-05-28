"""NodeService — business logic for node check-in operations."""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from src.domain.job import Job
from src.domain.node import Node

logger = logging.getLogger(__name__)


@runtime_checkable
class NodeDatastore(Protocol):
    """Protocol for node-related datastore operations."""

    async def update_node(self, node: Node) -> Node: ...

    def get_next_job(self, node_id: str) -> Job | None: ...


class NodeService:
    """Business logic for node-related endpoints."""

    def __init__(self, datastore: NodeDatastore) -> None:
        self._store = datastore

    async def checkin(self, node: Node) -> tuple[Node, Job | None]:
        """Process a node check-in: update the node, then fetch its next job."""
        updated = await self._store.update_node(node)
        job = self._store.get_next_job(updated.id)
        return updated, job
