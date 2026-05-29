"""ElasticCasestore case CRUD + history unit tests (mocked AsyncElasticsearch).

Ports the case-side behavior of ``server/modules/elastic/elasticcasestore.go``
(``validateCase``, ``save``/``get``/``getAll``, ``Create``/``Update``/``GetCase``/
``GetCaseHistory``) and the byte-pinned assertions from
``elasticcasestore_test.go``.

Divergence from Go (matches the port): the ``Casestore`` port takes no ``ctx``
and performs no ``CheckAuthorized`` — authorization happens at the route layer —
and the requestor id is supplied to the constructor.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.adapters.elasticsearch.casestore import ElasticCasestore
from src.adapters.elasticsearch.client import ElasticClients
from src.adapters.elasticsearch.config import ElasticConfig
from src.adapters.elasticsearch.eventstore import ElasticEventstore
from src.domain.case import Case
from src.domain.event import EventSearchCriteria, EventSearchResults

# Go uses Init("myIndex", "myAuditIndex", 45, "so_", ...) in the case tests, so
# pin the same index names here to assert the exact Lucene query strings.
_CFG = ElasticConfig(
    case_index="myIndex",
    audit_index="myAuditIndex",
    max_case_associations=45,
    schema_prefix="so_",
)


class _RecordingEventstore(ElasticEventstore):
    """Eventstore that records the search criteria (Go's FakeEventstore).

    Mirrors ``server.NewFakeEventstore`` capturing ``InputSearchCriterias`` so
    tests can assert the literal ``RawQuery`` Go pins, while still running the
    real search/convert pipeline against the mocked client.
    """

    def __init__(
        self,
        clients: ElasticClients,
        config: ElasticConfig,
        requestor_id: str = "",
    ) -> None:
        super().__init__(clients, config, requestor_id)
        self.input_criterias: list[EventSearchCriteria] = []

    async def search(self, criteria: EventSearchCriteria) -> EventSearchResults:
        self.input_criterias.append(criteria)
        return await super().search(criteria)


def _store(es: AsyncMock) -> ElasticCasestore:
    eventstore = _RecordingEventstore(
        ElasticClients(primary=es), _CFG, requestor_id="myRequestorId",
    )
    return ElasticCasestore(
        ElasticClients(primary=es), _CFG, requestor_id="myRequestorId",
        eventstore=eventstore,
    )


def _recorder(store: ElasticCasestore) -> _RecordingEventstore:
    eventstore = store._eventstore
    assert isinstance(eventstore, _RecordingEventstore)
    return eventstore


def _field_caps(es: AsyncMock) -> None:
    es.field_caps.return_value = {"fields": {}}


def _case_hit(doc_id: str = "live1", status: str = "new") -> dict[str, object]:
    return {
        "_index": "so-case",
        "_id": doc_id,
        "_source": {
            "so_kind": "case",
            "so_case": {"title": "T", "status": status, "description": "d"},
        },
    }


def _search_hits(*hits: dict[str, object]) -> dict[str, object]:
    return {
        "took": 1,
        "timed_out": False,
        "hits": {"total": len(hits), "hits": list(hits)},
    }


# ---------------------------------------------------------------------------
# validate_case — exact error strings pinned by elasticcasestore_test.go
# ---------------------------------------------------------------------------


def test_validate_case_invalid_id() -> None:
    c = Case()
    c.id = "this is an invalid id"
    assert _store(AsyncMock()).validate_case(c) == "invalid ID for caseId"


def test_validate_case_invalid_user_id() -> None:
    c = Case()
    c.user_id = "this is an invalid id"
    assert _store(AsyncMock()).validate_case(c) == "invalid ID for userId"


def test_validate_case_invalid_assignee_id() -> None:
    c = Case()
    c.assignee_id = "this is an invalid id"
    assert _store(AsyncMock()).validate_case(c) == "invalid ID for assigneeId"


def test_validate_case_title_too_long() -> None:
    c = Case()
    c.title = "this is my unreasonably long title\n" * 4
    c.status = "myStatus"
    c.description = "myDescription"
    assert _store(AsyncMock()).validate_case(c) == "title is too long (140/100)"


def test_validate_case_status_too_long() -> None:
    c = Case()
    c.title = "myTitle"
    c.status = "this is my unreasonably long status\n" * 4
    c.description = "myDescription"
    assert _store(AsyncMock()).validate_case(c) == "status is too long (144/100)"


def test_validate_case_invalid_priority() -> None:
    c = Case()
    c.title = "myTitle"
    c.status = "myStatus"
    c.description = "myDescription"
    c.priority = -12
    assert _store(AsyncMock()).validate_case(c) == "Invalid priority"


def test_validate_case_kind_must_not_be_specified() -> None:
    c = Case()
    c.title = "myTitle"
    c.status = "myStatus"
    c.description = "myDescription"
    c.kind = "myKind"
    assert _store(AsyncMock()).validate_case(c) == "Field 'Kind' must not be specified"


def test_validate_case_operation_must_not_be_specified() -> None:
    c = Case()
    c.title = "myTitle"
    c.status = "myStatus"
    c.description = "myDescription"
    c.operation = "myOperation"
    assert (
        _store(AsyncMock()).validate_case(c)
        == "Field 'Operation' must not be specified"
    )


def test_validate_case_tag_too_long() -> None:
    c = Case()
    c.title = "myTitle"
    c.status = "myStatus"
    c.description = "myDescription"
    c.tags = ["this is my unreasonably long tag\n" * 4]
    assert _store(AsyncMock()).validate_case(c) == "tag[0] is too long (132/100)"


def test_validate_case_excessive_tags() -> None:
    c = Case()
    c.title = "myTitle"
    c.status = "myStatus"
    c.description = "myDescription"
    c.tags = ["myTag"] * 499
    assert (
        _store(AsyncMock()).validate_case(c)
        == "Field 'tags' contains excessive elements (499/50)"
    )


def test_validate_case_mutates_severity() -> None:
    # convertSeverity: "3" -> "high"
    c = Case()
    c.title = "myTitle"
    c.status = "myStatus"
    c.description = "myDescription"
    c.severity = "3"
    assert _store(AsyncMock()).validate_case(c) is None
    assert c.severity == "high"


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


async def test_create_rejects_invalid_id() -> None:
    # Go TestCreateError: an invalid (too-short) id fails validateCase first.
    es = AsyncMock()
    case = Case()
    case.id = "123"
    case.title = "T"
    case.status = "x"
    case.description = "d"
    with pytest.raises(Exception, match="invalid ID for caseId"):
        await _store(es).create(case)


async def test_create_rejects_supplied_valid_id() -> None:
    # Go Create: a *valid* id passes validateCase but is rejected as unexpected.
    es = AsyncMock()
    case = Case()
    case.id = "abc12"
    case.title = "T"
    case.status = "x"
    case.description = "d"
    with pytest.raises(Exception, match="Unexpected ID found in new case"):
        await _store(es).create(case)


async def test_create_indexes_live_and_audit_then_reads_back() -> None:
    es = AsyncMock()
    _field_caps(es)
    es.index.return_value = {"_id": "live1", "result": "created"}
    es.search.return_value = _search_hits(_case_hit())
    case = Case()
    case.title = "T"
    case.status = "x"
    case.description = "d"
    created = await _store(es).create(case)
    assert created is not None
    assert created.id == "live1"
    assert es.index.await_count == 2  # live + audit
    # Status forced to 'new' on create
    assert created.status == "new"
    # Live write strips the cross-cluster prefix; audit goes to the audit index.
    assert es.index.await_args_list[0].kwargs["index"] == "myIndex"
    assert es.index.await_args_list[1].kwargs["index"] == "myAuditIndex"
    assert es.index.await_args_list[1].kwargs["document"]["so_operation"] == "create"


async def test_create_omits_supplied_id_on_live_index() -> None:
    es = AsyncMock()
    _field_caps(es)
    es.index.return_value = {"_id": "live1", "result": "created"}
    es.search.return_value = _search_hits(_case_hit())
    case = Case()
    case.title = "T"
    case.status = "x"
    case.description = "d"
    await _store(es).create(case)
    # prepare_for_save clears the id, so the live index call carries no id kwarg.
    assert "id" not in es.index.await_args_list[0].kwargs
    # requestor id stamped onto the live document.
    live_doc = es.index.await_args_list[0].kwargs["document"]
    assert live_doc["so_case"]["userId"] == "myRequestorId"


# ---------------------------------------------------------------------------
# get_case / get (read-back search query)
# ---------------------------------------------------------------------------


async def test_get_case_invalid_id() -> None:
    es = AsyncMock()
    with pytest.raises(Exception, match="invalid ID for caseId"):
        await _store(es).get_case("ab")  # too short


async def test_get_case_builds_lucene_query() -> None:
    es = AsyncMock()
    _field_caps(es)
    es.search.return_value = _search_hits(_case_hit("myCaseId"))
    store = _store(es)
    case = await store.get_case("myCaseId")
    assert case is not None
    # Raw query interpolated exactly as Go's get() builds it (Go asserts on the
    # criteria RawQuery, not the reconstructed query_string).
    recorder = _recorder(store)
    assert len(recorder.input_criterias) == 1
    assert (
        recorder.input_criterias[0].raw_query
        == '_index:"myIndex" AND so_kind:"case" AND _id:"myCaseId"'
    )


async def test_get_case_not_found_raises() -> None:
    es = AsyncMock()
    _field_caps(es)
    es.search.return_value = _search_hits()  # no hits
    with pytest.raises(Exception, match="Object not found"):
        await _store(es).get_case("myCaseId")


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


async def test_update_missing_id() -> None:
    es = AsyncMock()
    case = Case()
    case.title = "myTitle"
    case.status = "myStatus"
    case.description = "myDesc"
    with pytest.raises(Exception, match="Missing case ID"):
        await _store(es).update(case)


async def test_update_reads_old_then_saves_then_reads_back() -> None:
    es = AsyncMock()
    _field_caps(es)
    es.index.return_value = {"_id": "myCaseId", "result": "updated"}
    es.search.return_value = _search_hits(_case_hit("myCaseId", status="open"))
    case = Case()
    case.id = "myCaseId"
    case.title = "T"
    case.status = "open"
    case.description = "d"
    updated = await _store(es).update(case)
    assert updated is not None
    assert updated.id == "myCaseId"
    assert es.index.await_count == 2  # live + audit
    assert es.index.await_args_list[1].kwargs["document"]["so_operation"] == "update"


# ---------------------------------------------------------------------------
# get_case_history
# ---------------------------------------------------------------------------


async def test_get_case_history_invalid_id() -> None:
    es = AsyncMock()
    with pytest.raises(Exception, match="invalid ID for caseId"):
        await _store(es).get_case_history("ab")


async def test_get_case_history_builds_audit_query() -> None:
    es = AsyncMock()
    _field_caps(es)
    es.search.return_value = _search_hits(_case_hit("myCaseId"))
    store = _store(es)
    history = await store.get_case_history("myCaseId")
    assert len(history) == 1
    expected = (
        '_index:"myAuditIndex" AND (so_audit_doc_id:"myCaseId" OR '
        'so_comment.caseId:"myCaseId" OR so_related.caseId:"myCaseId" OR '
        'so_artifact.caseId:"myCaseId") | sortby @timestamp^'
    )
    recorder = _recorder(store)
    assert len(recorder.input_criterias) == 1
    assert recorder.input_criterias[0].raw_query == expected
