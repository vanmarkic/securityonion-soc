"""Unit tests for ElasticDetectionstore comment methods (Task 17).

Ports the relevant ``elasticdetectionstore_test.go`` comment cases:
``validateComment`` (order + pinned error strings), ``CreateComment``
(reject supplied id, require detection id, parent ``GetDetection`` check,
create-time stamp + read-back), ``GetComment`` (``validate_id`` on commentId),
``GetComments`` (``validate_id`` on detectionId + sortby createTime ascending),
``UpdateComment`` (require id, preserve createTime), ``DeleteComment`` (delete +
audit snapshot).

The async ES client is mocked with ``unittest.mock.AsyncMock`` (no live ES).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.adapters.elasticsearch.client import ElasticClients
from src.adapters.elasticsearch.config import ElasticConfig
from src.adapters.elasticsearch.detectionstore import ElasticDetectionstore
from src.domain.detection import DetectionComment

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


def _detection_hit(doc_id: str = "abcde") -> dict:
    return _hit(
        doc_id,
        {"so_kind": "detection",
         "so_detection": {"publicId": "100", "engine": "suricata"}},
    )


def _comment_hit(doc_id: str = "cmt12", detection_id: str = "abcde") -> dict:
    return _hit(
        doc_id,
        {"so_kind": "detectioncomment",
         "so_detectioncomment": {"value": "hello", "detectionId": detection_id}},
    )


def _valid_comment() -> DetectionComment:
    c = DetectionComment()
    c.detection_id = "abcde"
    c.value = "hello"
    return c


def _async_es():
    es = AsyncMock()
    # field_caps is hit by the composed eventstore's cache refresh.
    es.field_caps.return_value = {"fields": {}}
    return es


# ---------------------------------------------------------------------------
# validate_comment (Go validateComment)
# ---------------------------------------------------------------------------


def test_validate_comment_invalid_id():
    store = _store(_async_es())
    c = _valid_comment()
    c.id = "this is an invalid id"
    assert store.validate_comment(c) == "invalid ID for commentId"


def test_validate_comment_invalid_detection_id():
    store = _store(_async_es())
    c = _valid_comment()
    c.detection_id = "this is an invalid detection id"
    assert store.validate_comment(c) == "invalid ID for detectionId"


def test_validate_comment_invalid_user_id():
    store = _store(_async_es())
    c = _valid_comment()
    c.user_id = "this is an invalid user id"
    assert store.validate_comment(c) == "invalid ID for userId"


def test_validate_comment_kind_must_not_be_specified():
    store = _store(_async_es())
    c = _valid_comment()
    c.kind = "myKind"
    assert store.validate_comment(c) == "Field 'Kind' must not be specified"


def test_validate_comment_operation_must_not_be_specified():
    store = _store(_async_es())
    c = _valid_comment()
    c.operation = "create"
    assert store.validate_comment(c) == "Field 'Operation' must not be specified"


def test_validate_comment_value_required():
    store = _store(_async_es())
    c = _valid_comment()
    c.value = ""
    assert store.validate_comment(c) == "value is too short (0/1)"


def test_validate_comment_ok():
    store = _store(_async_es())
    assert store.validate_comment(_valid_comment()) is None


# ---------------------------------------------------------------------------
# create_comment
# ---------------------------------------------------------------------------


async def test_create_comment_rejects_supplied_id():
    es = _async_es()
    c = _valid_comment()
    c.id = "abcde"
    with pytest.raises(Exception, match="Unexpected ID found in new comment"):
        await _store(es).create_comment(c)


async def test_create_comment_requires_detection_id():
    es = _async_es()
    c = _valid_comment()
    c.detection_id = ""
    with pytest.raises(Exception, match="Missing Detection ID in new comment"):
        await _store(es).create_comment(c)


async def test_create_comment_checks_parent_detection_exists():
    es = _async_es()
    # parent GetDetection -> _get -> _get_all -> search returns no detection
    es.search.return_value = _search([])
    with pytest.raises(Exception, match="Object not found"):
        await _store(es).create_comment(_valid_comment())


async def test_create_comment_indexes_live_and_audit_then_reads_back():
    es = _async_es()
    es.search.side_effect = [
        _search([_detection_hit()]),   # parent GetDetection
        _search([_comment_hit()]),     # read-back GetComment
    ]
    es.index.return_value = {"_id": "cmt12", "result": "created"}
    created = await _store(es).create_comment(_valid_comment())
    assert created.id == "cmt12"
    assert created.value == "hello"
    assert es.index.await_count == 2  # live + audit


# ---------------------------------------------------------------------------
# get_comment / get_comments
# ---------------------------------------------------------------------------


async def test_get_comment_invalid_id():
    es = _async_es()
    with pytest.raises(Exception, match="invalid ID for commentId"):
        await _store(es).get_comment("ab")  # too short


async def test_get_comment_reads_back():
    es = _async_es()
    es.search.return_value = _search([_comment_hit()])
    c = await _store(es).get_comment("cmt12")
    assert c.id == "cmt12"
    assert c.detection_id == "abcde"


async def test_get_comments_invalid_detection_id():
    es = _async_es()
    with pytest.raises(Exception, match="invalid ID for detectionId"):
        await _store(es).get_comments("ab")  # too short


async def test_get_comments_query_and_sort():
    es = _async_es()
    es.search.return_value = _search([_comment_hit()])
    comments = await _store(es).get_comments("abcde")
    assert len(comments) == 1
    assert comments[0].detection_id == "abcde"
    # the eventstore search built the by-detectionId query with createTime sort
    # (the createTime^ sortby segment -> ascending sort on the request body).
    sort = es.search.await_args_list[-1].kwargs["sort"]
    assert sort is not None
    assert sort[0] == {
        "so_detectioncomment.createTime": {
            "order": "asc", "missing": "_last", "unmapped_type": "date",
        },
    }


# ---------------------------------------------------------------------------
# update_comment
# ---------------------------------------------------------------------------


async def test_update_comment_requires_id():
    es = _async_es()
    c = _valid_comment()  # id == ""
    with pytest.raises(Exception, match="Missing comment ID"):
        await _store(es).update_comment(c)


async def test_update_comment_reads_back():
    es = _async_es()
    es.index.return_value = {"_id": "cmt12", "result": "updated"}
    es.search.side_effect = [
        _search([_comment_hit()]),  # old GetComment (preserve createTime)
        _search([_comment_hit()]),  # read-back GetComment
    ]
    c = _valid_comment()
    c.id = "cmt12"
    updated = await _store(es).update_comment(c)
    assert updated.id == "cmt12"
    assert es.index.await_count == 2  # live + audit


# ---------------------------------------------------------------------------
# delete_comment
# ---------------------------------------------------------------------------


async def test_delete_comment_reads_then_deletes():
    es = _async_es()
    es.search.return_value = _search([_comment_hit()])
    es.delete.return_value = {"_id": "cmt12", "result": "deleted"}
    es.index.return_value = {"_id": "audit1", "result": "created"}
    result = await _store(es).delete_comment("cmt12")
    assert result is None
    assert es.delete.await_count == 1
    assert es.index.await_count == 1  # audit snapshot
