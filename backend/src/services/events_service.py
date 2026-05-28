"""EventsService — business logic for event search and acknowledgement."""

from __future__ import annotations

import logging

from src.domain.event import (
    EventAckCriteria,
    EventSearchCriteria,
    EventSearchResults,
    EventUpdateResults,
)
from src.ports.events import Eventstore

logger = logging.getLogger(__name__)


class EventsService:
    """Business logic for event-related endpoints."""

    def __init__(self, eventstore: Eventstore | None) -> None:
        self._store = eventstore

    @property
    def is_eventstore_configured(self) -> bool:
        return self._store is not None

    async def search(self, criteria: EventSearchCriteria) -> EventSearchResults:
        return await self._store.search(criteria)

    async def acknowledge(self, criteria: EventAckCriteria) -> EventUpdateResults:
        return await self._store.acknowledge(criteria)
