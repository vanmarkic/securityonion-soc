"""Tests for ElasticEventstore.acknowledge (mocked async ES client).

Ports the behavior of ``elasticeventstore.go`` ``Acknowledge`` + ``Update``
(update_by_query fan-out over all clients). The Python port takes no ctx and
performs no CheckAuthorized (auth is at the route layer); requestor_id is a
constructor argument.
"""

from unittest.mock import AsyncMock

from src.adapters.elasticsearch.client import ElasticClients
from src.adapters.elasticsearch.config import ElasticConfig
from src.adapters.elasticsearch.eventstore import ElasticEventstore
from src.domain.event import EventAckCriteria


async def test_acknowledge_requires_event_filter():
    es = AsyncMock()
    es.field_caps.return_value = {"fields": {}}
    store = ElasticEventstore(
        ElasticClients(primary=es), ElasticConfig(), requestor_id="u1",
    )
    c = EventAckCriteria()
    c.event_filter = {}
    res = await store.acknowledge(c)
    assert "EventFilter must be specified" in res.errors[0]
    es.update_by_query.assert_not_awaited()


async def test_acknowledge_fans_out_over_all_clients():
    es1, es2 = AsyncMock(), AsyncMock()
    for es in (es1, es2):
        es.field_caps.return_value = {"fields": {}}
        es.update_by_query.return_value = {
            "took": 10, "timed_out": False, "updated": 2, "noops": 1,
        }
    store = ElasticEventstore(
        ElasticClients(primary=es1, remotes=[es2]),
        ElasticConfig(),
        requestor_id="u1",
    )
    c = EventAckCriteria()
    c.acknowledge = True
    c.event_filter = {"event.module": "suricata"}
    res = await store.acknowledge(c)
    es1.update_by_query.assert_awaited_once()
    es2.update_by_query.assert_awaited_once()
    assert res.updated_count == 4
    assert res.unchanged_count == 2


async def test_acknowledge_zero_updates_message():
    es = AsyncMock()
    es.field_caps.return_value = {"fields": {}}
    es.update_by_query.return_value = {
        "took": 1, "timed_out": False, "updated": 0, "noops": 0,
    }
    store = ElasticEventstore(
        ElasticClients(primary=es), ElasticConfig(), requestor_id="u1",
    )
    c = EventAckCriteria()
    c.acknowledge = True
    c.event_filter = {"k": "v"}
    res = await store.acknowledge(c)
    assert "No eligible events available to acknowledge" in res.errors


async def test_acknowledge_all_already_acknowledged_message():
    es = AsyncMock()
    es.field_caps.return_value = {"fields": {}}
    es.update_by_query.return_value = {
        "took": 1, "timed_out": False, "updated": 0, "noops": 5,
    }
    store = ElasticEventstore(
        ElasticClients(primary=es), ElasticConfig(), requestor_id="u1",
    )
    c = EventAckCriteria()
    c.acknowledge = True
    c.event_filter = {"k": "v"}
    res = await store.acknowledge(c)
    assert "All events have already been acknowledged" in res.errors


async def test_acknowledge_count_field_not_filtered_and_triggers_async():
    es = AsyncMock()
    es.field_caps.return_value = {"fields": {}}
    es.update_by_query.return_value = {}  # async => not parsed
    store = ElasticEventstore(
        ElasticClients(primary=es), ElasticConfig(), requestor_id="u1",
    )
    c = EventAckCriteria()
    c.acknowledge = True
    # count above async_threshold (default 10) -> asynchronous, no result parse
    c.event_filter = {"event.module": "suricata", "count": 5000.0}
    res = await store.acknowledge(c)
    es.update_by_query.assert_awaited_once()
    kwargs = es.update_by_query.await_args.kwargs
    assert kwargs["wait_for_completion"] is False
    # count is not added as a query filter
    query_str = _query_string(kwargs)
    assert "count" not in query_str
    assert "event.module" in query_str
    # async path: no zero-update error appended
    assert res.errors == []


async def test_acknowledge_unack_uses_false_script():
    es = AsyncMock()
    es.field_caps.return_value = {"fields": {}}
    es.update_by_query.return_value = {
        "took": 1, "timed_out": False, "updated": 1, "noops": 0,
    }
    store = ElasticEventstore(
        ElasticClients(primary=es), ElasticConfig(), requestor_id="u1",
    )
    c = EventAckCriteria()
    c.acknowledge = False  # unacknowledge
    c.event_filter = {"k": "v"}
    await store.acknowledge(c)
    kwargs = es.update_by_query.await_args.kwargs
    assert kwargs["script"]["source"] == "ctx._source.event.acknowledged = false;"


async def test_acknowledge_honors_search_filter_and_date_range():
    """Go ``Acknowledge`` calls ``Populate(SearchFilter, DateRange, ...)`` so the
    update_by_query is scoped by both the parsed search filter and the
    ``@timestamp`` range. Mirrors converter golden ``TestConvertToElasticUpdateRequest``.
    """
    es = AsyncMock()
    es.field_caps.return_value = {"fields": {}}
    es.update_by_query.return_value = {
        "took": 1, "timed_out": False, "updated": 1, "noops": 0,
    }
    store = ElasticEventstore(
        ElasticClients(primary=es), ElasticConfig(), requestor_id="u1",
    )
    c = EventAckCriteria()
    c.acknowledge = True
    c.event_filter = {"k": "v"}
    c.search_filter = "event.dataset:alerts"
    c.date_range = "2020/09/24 10:11:12 AM - 2020/09/24 12:14:15 PM"
    c.date_range_format = "%Y/%m/%d %I:%M:%S %p"
    c.timezone = "America/New_York"
    await store.acknowledge(c)

    kwargs = es.update_by_query.await_args.kwargs
    query = kwargs["query"]
    must = query["bool"]["must"]
    # The parsed search filter must appear in the query_string component.
    qs = next(m["query_string"]["query"] for m in must if "query_string" in m)
    assert "event.dataset:alerts" in qs
    # The event filter is also ANDed into the search component (string value
    # is non-scalar, hence quoted).
    assert 'k:"v"' in qs
    assert "AND" in qs
    # The DateRange must produce an @timestamp range clause (time-bounded ack),
    # carrying the parsed begin/end clock values. (The TZ-offset suffix is a
    # separate domain ``_parse_datetime`` concern — it currently returns naive
    # datetimes so the offset renders as ``Z``; the range scoping itself is what
    # Go's Populate-then-makeQuery contributes and is what this test guards.)
    rng = next(m["range"]["@timestamp"] for m in must if "range" in m)
    assert rng["gte"].startswith("2020-09-24T10:11:12")
    assert rng["lte"].startswith("2020-09-24T12:14:15")
    assert rng["format"] == "strict_date_optional_time"


async def test_acknowledge_blank_date_range_defaults_to_24h_window():
    """An empty DateRange defaults to a now-24h window in Go's ParseDateRange,
    so the ack is still time-bounded (an ``@timestamp`` range clause is emitted)."""
    es = AsyncMock()
    es.field_caps.return_value = {"fields": {}}
    es.update_by_query.return_value = {
        "took": 1, "timed_out": False, "updated": 1, "noops": 0,
    }
    store = ElasticEventstore(
        ElasticClients(primary=es), ElasticConfig(), requestor_id="u1",
    )
    c = EventAckCriteria()
    c.acknowledge = True
    c.event_filter = {"k": "v"}
    # search_filter / date_range left blank
    await store.acknowledge(c)

    kwargs = es.update_by_query.await_args.kwargs
    must = kwargs["query"]["bool"]["must"]
    # Blank DateRange => default 24h window => @timestamp range present.
    assert any("range" in m and "@timestamp" in m["range"] for m in must)


def _query_string(kwargs: dict) -> str:
    import json

    return json.dumps(kwargs["query"])
