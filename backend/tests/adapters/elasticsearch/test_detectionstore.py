"""Unit tests for ElasticDetectionstore (Task 16).

Ports the relevant ``elasticdetectionstore_test.go`` cases: detection validation
(order + pinned error strings), CRUD with audit dual-write + read-after-write,
deterministic ``to_uuid`` ids, get-by-public-id, history (audit-index query), and
template existence (404 -> False).

The async ES client is mocked with ``unittest.mock.AsyncMock`` (no live ES).
"""

from __future__ import annotations

import pytest

from src.adapters.elasticsearch.client import ElasticClients
from src.adapters.elasticsearch.config import ElasticConfig
from src.adapters.elasticsearch.detectionstore import ElasticDetectionstore
from src.adapters.elasticsearch.escaping import to_uuid
from src.domain.detection import Detection

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _store(es) -> ElasticDetectionstore:
    return ElasticDetectionstore(
        ElasticClients(primary=es), ElasticConfig(), requestor_id="u1",
    )


def _hit(doc_id: str, source: dict) -> dict:
    return {"_index": "so-detection", "_id": doc_id, "_source": source}


def _search(hits: list[dict]) -> dict:
    return {
        "took": 1,
        "timed_out": False,
        "hits": {"total": len(hits), "hits": hits},
    }


def _valid_detection() -> Detection:
    det = Detection()
    det.public_id = "100"
    det.engine = "suricata"
    det.language = "suricata"
    det.title = "t"
    det.author = "a"
    det.description = "d"
    det.content = "c"
    det.severity = "high"
    return det


# ---------------------------------------------------------------------------
# validation (Go validateDetection)
# ---------------------------------------------------------------------------


def test_validate_detection_invalid_id():
    store = _store(_async_es())
    det = _valid_detection()
    det.id = "this is an invalid id"
    assert store.validate_detection(det) == "invalid ID for Id"


def test_validate_detection_invalid_public_id():
    store = _store(_async_es())
    det = _valid_detection()
    det.public_id = "this is an invalid publicid"
    assert store.validate_detection(det) == "invalid ID for publicId"


def test_validate_detection_title_too_long():
    store = _store(_async_es())
    det = _valid_detection()
    det.title = "a" * 1_000_001
    assert store.validate_detection(det) == "title is too long (1000001/1000000)"


def test_validate_detection_author_too_long():
    store = _store(_async_es())
    det = _valid_detection()
    det.author = "a" * 251
    assert store.validate_detection(det) == "author is too long (251/250)"


def test_validate_detection_invalid_engine():
    store = _store(_async_es())
    det = _valid_detection()
    det.engine = "myEngine"
    assert store.validate_detection(det) == "invalid engine"


def test_validate_detection_invalid_language():
    store = _store(_async_es())
    det = _valid_detection()
    det.language = "Spanish"
    assert store.validate_detection(det) == "invalid language"


def test_validate_detection_engine_language_mismatch():
    store = _store(_async_es())
    det = _valid_detection()
    det.engine = "suricata"
    det.language = "yara"
    assert store.validate_detection(det) == "engine and language mismatch"


def test_validate_detection_kind_must_not_be_specified():
    store = _store(_async_es())
    det = _valid_detection()
    det.kind = "myKind"
    assert store.validate_detection(det) == "Field 'Kind' must not be specified"


# ---------------------------------------------------------------------------
# create / update / get / delete / public-id / history / template
# ---------------------------------------------------------------------------


async def test_create_duplicate_public_id_raises_already_exists():
    es = _async_es()
    es.search.return_value = _search([
        _hit("d1", {"so_kind": "detection",
                    "so_detection": {"publicId": "100", "engine": "suricata"}}),
    ])
    det = _valid_detection()
    with pytest.raises(Exception, match="already exists"):
        await _store(es).create_detection(det)


async def test_create_detection_sets_deterministic_uuid_id():
    es = _async_es()
    es.search.side_effect = [
        _search([]),  # dup-check empty
        _search([_hit(  # read-back
            to_uuid("100"),
            {"so_kind": "detection",
             "so_detection": {"publicId": "100", "engine": "suricata"}},
        )]),
    ]
    es.index.return_value = {"_id": to_uuid("100"), "result": "created"}
    created = await _store(es).create_detection(_valid_detection())
    assert created.id == to_uuid("100")
    assert es.index.await_count == 2  # live + audit


async def test_create_rejects_supplied_id():
    es = _async_es()
    det = _valid_detection()
    det.id = "abcde"
    with pytest.raises(Exception, match="Unexpected ID found in new comment"):
        await _store(es).create_detection(det)


async def test_get_detection_invalid_id():
    es = _async_es()
    with pytest.raises(Exception, match="invalid ID for detectId"):
        await _store(es).get_detection("ab")  # too short


async def test_get_detection_by_public_id_returns_first():
    es = _async_es()
    es.search.return_value = _search([
        _hit("d1", {"so_kind": "detection",
                    "so_detection": {"publicId": "100", "engine": "suricata"}}),
    ])
    det = await _store(es).get_detection_by_public_id("100")
    assert det is not None
    assert det.public_id == "100"


async def test_get_detection_by_public_id_none_when_empty():
    es = _async_es()
    es.search.return_value = _search([])
    assert await _store(es).get_detection_by_public_id("100") is None


async def test_update_detection_requires_id():
    es = _async_es()
    det = _valid_detection()  # id == ""
    with pytest.raises(Exception, match="Missing detection onion ID"):
        await _store(es).update_detection(det)


async def test_update_detection_reads_back():
    es = _async_es()
    es.index.return_value = {"_id": to_uuid("100"), "result": "updated"}
    es.search.return_value = _search([_hit(
        to_uuid("100"),
        {"so_kind": "detection",
         "so_detection": {"publicId": "100", "engine": "suricata"}},
    )])
    det = _valid_detection()
    det.id = to_uuid("100")
    updated = await _store(es).update_detection(det)
    assert updated.id == to_uuid("100")
    assert es.index.await_count == 2  # live + audit


async def test_delete_detection_reads_then_deletes():
    es = _async_es()
    es.search.return_value = _search([_hit(
        to_uuid("100"),
        {"so_kind": "detection",
         "so_detection": {"publicId": "100", "engine": "suricata"}},
    )])
    es.delete.return_value = {"_id": to_uuid("100"), "result": "deleted"}
    es.index.return_value = {"_id": "audit1", "result": "created"}
    deleted = await _store(es).delete_detection(to_uuid("100"))
    assert deleted.public_id == "100"
    assert es.delete.await_count == 1
    assert es.index.await_count == 1  # audit snapshot


async def test_get_detection_history_queries_audit_index():
    es = _async_es()
    es.search.return_value = _search([])
    await _store(es).get_detection_history("100")
    # the read-back search ran against the eventstore search path
    assert es.search.await_count == 1


async def test_does_template_exist_404_false():
    from elasticsearch import NotFoundError
    es = _async_es()
    es.indices.get_index_template.side_effect = NotFoundError(
        "m", meta=None, body=None,
    )
    assert await _store(es).does_template_exist("myTemplate") is False


async def test_does_template_exist_200_true():
    es = _async_es()
    es.indices.get_index_template.return_value = {"index_templates": []}
    assert await _store(es).does_template_exist("myTemplate") is True


# ---------------------------------------------------------------------------
# AsyncMock client factory
# ---------------------------------------------------------------------------


def _async_es():
    from unittest.mock import AsyncMock
    es = AsyncMock()
    # field_caps is hit by the composed eventstore's cache refresh.
    es.field_caps.return_value = {"fields": {}}
    return es
