"""ES Eventstore integration test — real index/search round-trip.

Skipped when no live Elasticsearch is reachable (see conftest.es_available).
"""

from __future__ import annotations

import pytest
from elasticsearch import AsyncElasticsearch

from tests.adapters.elasticsearch.integration.conftest import es_available

pytestmark = pytest.mark.skipif(not es_available(), reason="no live Elasticsearch")


async def test_index_then_search_roundtrip(real_es: AsyncElasticsearch) -> None:
    from src.adapters.elasticsearch.client import ElasticClients
    from src.adapters.elasticsearch.config import ElasticConfig
    from src.adapters.elasticsearch.eventstore import ElasticEventstore
    from src.domain.event import EventSearchCriteria
    from src.domain.query import Query

    idx = "so-itest-events"
    try:
        await real_es.index(
            index=idx,
            document={
                "@timestamp": "2020-01-01T00:00:00.000Z",
                "event": {"module": "test"},
            },
            refresh="true",
        )
        cfg = ElasticConfig(index=idx)
        store = ElasticEventstore(ElasticClients(primary=real_es), cfg)
        c = EventSearchCriteria()
        c.metric_limit = 0
        c.event_limit = 25
        c.parsed_query = Query()
        c.parsed_query.parse("event.module:test")
        res = await store.search(c)
        assert res.total_events >= 1
    finally:
        await real_es.indices.delete(index=idx, ignore_unavailable=True)
