"""PacketService — business logic for PCAP packet retrieval."""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class PacketDatastore(Protocol):
    """Protocol for packet-related datastore operations."""

    async def get_packets(
        self, job_id: int, offset: int, count: int, unwrap: bool,
    ) -> list[dict[str, Any]]: ...


class PacketService:
    """Business logic for packet-related endpoints."""

    def __init__(
        self, datastore: PacketDatastore, *, max_packet_count: int = 5000,
    ) -> None:
        self._store = datastore
        self._max_count = max_packet_count

    @property
    def max_packet_count(self) -> int:
        return self._max_count

    async def get_packets(
        self, job_id: int, offset: int, count: int, unwrap: bool,
    ) -> list[dict[str, Any]]:
        # Cap count at the server maximum
        effective_count = count
        if effective_count <= 0 or effective_count > self._max_count:
            effective_count = self._max_count

        return await self._store.get_packets(job_id, offset, effective_count, unwrap)
