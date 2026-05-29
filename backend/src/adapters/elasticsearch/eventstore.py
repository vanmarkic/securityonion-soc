"""ElasticEventstore — ES-backed implementation of the Eventstore port.

Ports ``server/modules/elastic/elasticeventstore.go`` ``Search`` and
``Acknowledge`` / ``Update`` (update_by_query fan-out).

Divergence from Go: the Python ``Eventstore`` port (``src/ports/events.py``)
takes no ``ctx`` argument and performs no ``CheckAuthorized`` — authorization
happens at the FastAPI route/dependency layer — so the Go ``server.CheckAuthorized``
calls and the ``es-security-runas-user`` per-request header are dropped here.
The acknowledging-user id is supplied to the constructor as ``requestor_id``
instead of being read from the Go request context.

``acknowledge`` faithfully reproduces Go's ``updateCriteria.Populate`` step:
the ack ``search_filter`` is parsed into the update query and ``date_range``
sets the ``@timestamp`` begin/end bounds (defaulting to a now-24h window when
blank), so the resulting ``update_by_query`` is search-scoped and time-bounded
exactly as Go is. (One residual, pre-existing limitation lives in the shared
``domain.event._parse_datetime`` date parser, ported under an earlier task: it
returns naive datetimes, so an explicit timezone offset renders as ``Z`` rather
than e.g. ``-04:00``. That affects every date-range consumer, not just ack, and
is out of scope for this adapter.)
"""

from __future__ import annotations

import time
from typing import Any

from src.adapters.elasticsearch.ack_scripts import (
    build_acknowledge_script,
    build_unacknowledge_script,
)
from src.adapters.elasticsearch.client import ElasticClients
from src.adapters.elasticsearch.config import ElasticConfig
from src.adapters.elasticsearch.converter import (
    parse_search_results,
    parse_update_results,
)
from src.adapters.elasticsearch.field_caps import FieldCapsCache, map_elastic_field
from src.adapters.elasticsearch.helpers import disable_cross_cluster_index
from src.adapters.elasticsearch.query_builder import (
    build_search_request,
    build_update_request,
)
from src.domain.event import (
    EventAckCriteria,
    EventSearchCriteria,
    EventSearchResults,
    EventUpdateCriteria,
    EventUpdateResults,
)
from src.domain.query import (
    SEGMENT_KIND_SEARCH,
    Query,
    SearchSegment,
    is_scalar,
)


class ElasticEventstore:
    """Eventstore port backed by one or more ``AsyncElasticsearch`` clients."""

    def __init__(
        self,
        clients: ElasticClients,
        config: ElasticConfig,
        requestor_id: str = "",
    ) -> None:
        self._clients = clients
        self._config = config
        self._requestor_id = requestor_id
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

    async def acknowledge(self, criteria: EventAckCriteria) -> EventUpdateResults:
        results = EventUpdateResults()
        if not criteria.event_filter:
            # Go: "EventFilter must be specified to ack an event"
            results.errors.append("EventFilter must be specified to ack an event")
            results.complete()
            return results

        await self._refresh_cache()
        update_criteria = self._build_update_criteria_from_ack(criteria)
        await self._update(update_criteria, results)

        # Synchronous path only: map zero-update outcomes to a friendly error.
        if not update_criteria.asynchronous and not results.errors:
            if results.updated_count == 0:
                if results.unchanged_count == 0:
                    results.errors.append(
                        "No eligible events available to acknowledge",
                    )
                else:
                    results.errors.append(
                        "All events have already been acknowledged",
                    )

        results.complete()
        return results

    def _build_update_criteria_from_ack(
        self, criteria: EventAckCriteria,
    ) -> EventUpdateCriteria:
        """Mirror Go ``Acknowledge`` setup: build scripts, params, and the
        baselined search-only query from the ack search filter + event filter.

        Go ``Acknowledge`` calls ``updateCriteria.Populate(SearchFilter,
        DateRange, DateRangeFormat, Timezone, "0", "0")`` before reading the
        ``search`` segment. ``Populate`` (a) sets ``BeginTime``/``EndTime`` from
        the date range via ``util.ParseDateRange`` (which defaults to a now-24h
        window when the range is blank), and (b) parses ``SearchFilter`` into the
        ``ParsedQuery`` so the search segment seeds the update query. Both bounds
        and the parsed filter flow through ``build_update_request`` →
        ``make_query`` (``@timestamp`` range + ``query_string``). Go ignores the
        error returned by ``Populate`` (a blank ``SearchFilter`` yields
        ``ERROR_QUERY_INVALID__SEARCH_MISSING`` but the time bounds are still
        set), so we ignore it too.
        """
        update_criteria = EventUpdateCriteria()
        now_millis = int(time.time() * 1000)

        if criteria.acknowledge:
            scripts, params = build_acknowledge_script(
                now_millis=now_millis,
                escalate=criteria.escalate,
                user_id=self._requestor_id,
            )
        else:
            scripts, params = build_unacknowledge_script()
        update_criteria.update_scripts = list(scripts)
        update_criteria.params = dict(params)

        # Go: updateCriteria.Populate(SearchFilter, DateRange, ...). Sets
        # begin/end time bounds and parses the search filter; error ignored.
        update_criteria.populate(
            criteria.search_filter,
            criteria.date_range,
            criteria.date_range_format,
            criteria.timezone,
            "0",
            "0",
        )

        # Reuse the search segment parsed from SearchFilter (Go reuses
        # NamedSegment("search")); fall back to an empty segment when absent.
        existing = update_criteria.parsed_query.named_segment(SEGMENT_KIND_SEARCH)
        search_segment: SearchSegment
        if isinstance(existing, SearchSegment):
            search_segment = existing
        else:
            search_segment = SearchSegment.empty()

        update_criteria.asynchronous = False
        for key, value in criteria.event_filter.items():
            if key.lower() != "count":
                mapped = map_elastic_field(self._cache.defs, key)
                search_segment.add_filter(
                    mapped, f"{value}", is_scalar(value), True, False,
                )
            elif int(float(value)) > self._config.async_threshold:  # type: ignore[arg-type]
                update_criteria.asynchronous = True

        # Baseline the query to be based only on the search component.
        update_criteria.parsed_query = Query()
        update_criteria.parsed_query.add_segment(search_segment)
        return update_criteria

    async def _update(
        self, criteria: EventUpdateCriteria, results: EventUpdateResults,
    ) -> None:
        """Fan out update_by_query over all clients (Go ``Update``).

        Partial success is tolerated: errors are only surfaced if every host
        failed; otherwise successful hosts' counts accumulate.
        """
        body = build_update_request(self._cache.defs, criteria)
        indexes = [disable_cross_cluster_index(i) for i in self._indexes]
        errors: list[str] = []
        for client in self._clients.all_clients:
            try:
                resp = await client.update_by_query(
                    index=indexes,
                    query=body["query"],
                    script=body["script"],
                    conflicts="proceed",
                    refresh=True,
                    wait_for_completion=not criteria.asynchronous,
                )
            except Exception as exc:  # noqa: BLE001 — collect per-host failures
                errors.append(str(exc))
                continue
            if not criteria.asynchronous:
                sub = EventUpdateResults()
                err = parse_update_results(dict(resp), sub)
                if err:
                    errors.append(err)
                else:
                    results.add_event_update_results(sub)

        if errors and len(errors) >= len(self._clients.all_clients):
            results.errors.extend(errors)
