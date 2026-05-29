"""ElasticEventstore — ES-backed implementation of the Eventstore port.

Ports ``server/modules/elastic/elasticeventstore.go`` ``Search`` (this task).

Divergence from Go: the Python ``Eventstore`` port (``src/ports/events.py``)
takes no ``ctx`` argument and performs no ``CheckAuthorized`` — authorization
happens at the FastAPI route/dependency layer — so the Go ``server.CheckAuthorized``
calls and the ``es-security-runas-user`` per-request header are dropped here.
"""

from __future__ import annotations

from typing import Any

from src.adapters.elasticsearch.client import ElasticClients
from src.adapters.elasticsearch.config import ElasticConfig
from src.adapters.elasticsearch.converter import parse_search_results
from src.adapters.elasticsearch.field_caps import FieldCapsCache
from src.adapters.elasticsearch.query_builder import build_search_request
from src.domain.event import EventSearchCriteria, EventSearchResults


class ElasticEventstore:
    """Eventstore port backed by one or more ``AsyncElasticsearch`` clients."""

    def __init__(self, clients: ElasticClients, config: ElasticConfig) -> None:
        self._clients = clients
        self._config = config
        self._cache = FieldCapsCache(config.cache_ms)

    @property
    def _indexes(self) -> list[str]:
        # Go: strings.Split(store.index, ",")
        return self._config.index.split(",")

    async def _refresh_cache(self) -> None:
        async def fetch() -> dict[str, Any]:
            resp = await self._clients.read_client.field_caps(
                index=self._indexes, fields="*",
            )
            return dict(resp)

        await self._cache.refresh(fetch)

    async def search(self, criteria: EventSearchCriteria) -> EventSearchResults:
        results = EventSearchResults()
        await self._refresh_cache()
        body = build_search_request(self._cache.defs, self._config.intervals, criteria)
        resp = await self._clients.read_client.search(
            index=self._indexes,
            query=body.get("query"),
            aggs=body.get("aggs"),
            sort=body.get("sort"),
            size=body.get("size"),
            search_after=body.get("search_after"),
            track_total_hits=True,
            ignore_unavailable=True,
        )
        err = parse_search_results(self._cache.defs, dict(resp), results)
        if err:
            results.errors.append(err)
        results.criteria = criteria
        results.complete()
        return results
