"""ES Casestore integration test — real create/get round-trip.

Skipped when no live Elasticsearch is reachable (see conftest.es_available).
"""

from __future__ import annotations

import pytest
from elasticsearch import AsyncElasticsearch

from tests.adapters.elasticsearch.integration.conftest import es_available

pytestmark = pytest.mark.skipif(not es_available(), reason="no live Elasticsearch")


async def test_create_then_get_case_roundtrip(real_es: AsyncElasticsearch) -> None:
    from src.adapters.elasticsearch.casestore import ElasticCasestore
    from src.adapters.elasticsearch.client import ElasticClients
    from src.adapters.elasticsearch.config import ElasticConfig
    from src.domain.case import Case

    case_idx = "so-itest-case"
    audit_idx = "so-itest-casehistory"
    cfg = ElasticConfig(case_index=case_idx, audit_index=audit_idx)
    store = ElasticCasestore(ElasticClients(primary=real_es), cfg)

    try:
        created = await store.create(Case(title="integration round-trip"))
        assert created.id != ""
        # Refresh so the freshly-indexed doc is searchable for get_case.
        await real_es.indices.refresh(index=case_idx)

        fetched = await store.get_case(created.id)
        assert fetched is not None
        assert fetched.title == "integration round-trip"
        assert fetched.status == "new"
    finally:
        await real_es.indices.delete(index=case_idx, ignore_unavailable=True)
        await real_es.indices.delete(index=audit_idx, ignore_unavailable=True)
