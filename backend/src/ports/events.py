"""Eventstore port — defines the contract for event/query operations."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.domain.event import (
    EventSearchCriteria,
    EventSearchResults,
)


class QueryTask:
    """Represents an active query task in the event store."""

    def __init__(
        self,
        *,
        grid_id: str = "",
        task_id: str = "",
        details: str = "",
        start_time: str = "0001-01-01T00:00:00Z",
        elapsed_ms: int = 0,
        cancelable: bool = False,
    ) -> None:
        self.grid_id = grid_id
        self.task_id = task_id
        self.details = details
        self.start_time = start_time
        self.elapsed_ms = elapsed_ms
        self.cancelable = cancelable

    def to_dict(self) -> dict:
        return {
            "gridId": self.grid_id,
            "taskId": self.task_id,
            "details": self.details,
            "startTime": self.start_time,
            "elapsedMs": self.elapsed_ms,
            "cancelable": self.cancelable,
        }


@runtime_checkable
class Eventstore(Protocol):
    """Protocol that any event-storing adapter must satisfy."""

    async def search(
        self, criteria: EventSearchCriteria,
    ) -> EventSearchResults: ...

    async def get_active_queries(
        self, filter_internal: bool,
    ) -> list[QueryTask]: ...

    async def cancel_query(self, query_id: str) -> None: ...
