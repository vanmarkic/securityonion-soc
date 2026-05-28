"""QueryService — business logic for query operations."""

from __future__ import annotations

import logging

from src.domain.query import Query
from src.ports.events import Eventstore, QueryTask

logger = logging.getLogger(__name__)


class QueryNotFoundError(Exception):
    """Raised when a query to cancel is not found."""


class QueryService:
    """Business logic for query-related endpoints."""

    def __init__(self, eventstore: Eventstore, *, licensed: bool = True) -> None:
        self._store = eventstore
        self._licensed = licensed

    @property
    def is_licensed(self) -> bool:
        return self._licensed

    async def get_active_queries(self, filter_internal: bool) -> list[QueryTask]:
        return await self._store.get_active_queries(filter_internal)

    async def cancel_query(self, query_id: str) -> None:
        await self._store.cancel_query(query_id)

    @staticmethod
    def build_filtered_query(
        query_str: str, field: str, value: str, scalar: bool, mode: str,
        condense: bool,
    ) -> tuple[str, str | None]:
        query = Query()
        err = query.parse(query_str)
        if err is not None:
            return "", err

        if value:
            return query.filter(field, value, scalar, mode, condense)
        return str(query), None

    @staticmethod
    def build_grouped_query(
        query_str: str, field: str, group_idx: int,
    ) -> tuple[str, str | None]:
        query = Query()
        err = query.parse(query_str)
        if err is not None:
            return "", err
        return query.group(group_idx, field)

    @staticmethod
    def build_sorted_query(
        query_str: str, field: str,
    ) -> tuple[str, str | None]:
        query = Query()
        err = query.parse(query_str)
        if err is not None:
            return "", err
        return query.sort(field)
