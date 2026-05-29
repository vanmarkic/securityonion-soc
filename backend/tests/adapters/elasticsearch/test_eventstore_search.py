"""ElasticEventstore.search() unit tests (mocked AsyncElasticsearch client).

Ports the search-side behavior of ``server/modules/elastic/elasticeventstore.go``
``Search``: build the request body via the pure query builder, call the read
client's ``search`` with ``track_total_hits``/``ignore_unavailable`` over the
split index list, then map the response via the converter and ``complete()``.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock

from src.adapters.elasticsearch.client import ElasticClients
from src.adapters.elasticsearch.config import ElasticConfig
from src.adapters.elasticsearch.eventstore import ElasticEventstore
from src.domain.event import EventSearchCriteria
from src.domain.query import Query

FIX = Path(__file__).parent / "fixtures"


def _store(es: AsyncMock) -> ElasticEventstore:
    return ElasticEventstore(ElasticClients(primary=es), ElasticConfig())


async def test_search_calls_es_and_maps_results() -> None:
    es = AsyncMock()
    es.field_caps.return_value = {"fields": {}}
    es.search.return_value = json.loads((FIX / "converter_response.json").read_text())
    store = _store(es)

    c = EventSearchCriteria()
    c.metric_limit = 0
    c.event_limit = 25
    c.parsed_query = Query()
    c.parsed_query.parse("*")
    res = await store.search(c)

    assert res.total_events == 23689430
    assert len(res.events) == 25
    es.search.assert_awaited_once()
    kwargs = es.search.await_args.kwargs
    assert kwargs["track_total_hits"] is True
    assert kwargs["ignore_unavailable"] is True
    assert kwargs["index"] == ["*:so-*"]
    assert res.criteria is c
    assert res.complete_time > res.create_time  # complete() called


async def test_search_timeout_sets_error() -> None:
    es = AsyncMock()
    es.field_caps.return_value = {"fields": {}}
    es.search.return_value = {"took": 5, "timed_out": True, "hits": {}}
    store = _store(es)
    c = EventSearchCriteria()
    c.metric_limit = 0
    c.parsed_query = Query()
    c.parsed_query.parse("*")
    res = await store.search(c)
    assert "Timeout" in res.errors[0]
