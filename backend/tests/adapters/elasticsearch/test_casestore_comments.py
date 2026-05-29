"""ElasticCasestore comment CRUD unit tests (mocked AsyncElasticsearch).

Ports the comment-side behavior of ``server/modules/elastic/elasticcasestore.go``
(``validateComment``, ``CreateComment``/``GetComment``/``GetComments``/
``UpdateComment``/``DeleteComment``) and the byte-pinned assertions from
``elasticcasestore_test.go`` — the exact error strings, the
``so_comment.createTime^`` sortby, the by-id Lucene queries, and the
create-time-preserve-on-update behavior.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from src.adapters.elasticsearch.casestore import ElasticCasestore
from src.adapters.elasticsearch.client import ElasticClients
from src.adapters.elasticsearch.config import ElasticConfig
from src.adapters.elasticsearch.eventstore import ElasticEventstore
from src.domain.case import Comment
from src.domain.event import EventRecord, EventSearchCriteria, EventSearchResults

_CFG = ElasticConfig(
    case_index="myIndex",
    audit_index="myAuditIndex",
    max_case_associations=45,
    schema_prefix="so_",
)


class _ScriptedEventstore(ElasticEventstore):
    """Eventstore returning queued results in order (Go's FakeEventstore).

    Records each criteria's ``raw_query`` and returns the next queued
    ``EventSearchResults`` per ``search`` call, mirroring Go's
    ``FakeEventstore.SearchResults`` slice consumed in order.
    """

    def __init__(
        self,
        clients: ElasticClients,
        config: ElasticConfig,
        requestor_id: str = "",
    ) -> None:
        super().__init__(clients, config, requestor_id)
        self.input_criterias: list[EventSearchCriteria] = []
        self.results: list[EventSearchResults] = []

    def queue(self, *records: EventRecord) -> None:
        res = EventSearchResults()
        res.events = list(records)
        self.results.append(res)

    async def search(self, criteria: EventSearchCriteria) -> EventSearchResults:
        self.input_criterias.append(criteria)
        if self.results:
            return self.results.pop(0)
        return EventSearchResults()


def _store(es: AsyncMock) -> tuple[ElasticCasestore, _ScriptedEventstore]:
    eventstore = _ScriptedEventstore(
        ElasticClients(primary=es), _CFG, requestor_id="myRequestorId",
    )
    store = ElasticCasestore(
        ElasticClients(primary=es), _CFG, requestor_id="myRequestorId",
        eventstore=eventstore,
    )
    return store, eventstore


def _rec(kind: str, doc_id: str = "", **fields: object) -> EventRecord:
    rec = EventRecord()
    rec.id = doc_id
    rec.payload = {"so_kind": kind, **fields}
    return rec


# ---------------------------------------------------------------------------
# validate_comment — exact error strings pinned by elasticcasestore_test.go
# ---------------------------------------------------------------------------


def test_validate_comment_invalid_id() -> None:
    c = Comment()
    c.id = "this is an invalid id"
    store, _ = _store(AsyncMock())
    assert store.validate_comment(c) == "invalid ID for commentId"


def test_validate_comment_invalid_case_id() -> None:
    c = Comment()
    c.case_id = "this is an invalid id"
    store, _ = _store(AsyncMock())
    assert store.validate_comment(c) == "invalid ID for caseId"


def test_validate_comment_invalid_user_id() -> None:
    c = Comment()
    c.user_id = "this is an invalid id"
    store, _ = _store(AsyncMock())
    assert store.validate_comment(c) == "invalid ID for userId"


def test_validate_comment_kind_must_not_be_specified() -> None:
    c = Comment()
    c.description = "myDesc"
    c.kind = "myKind"
    store, _ = _store(AsyncMock())
    assert store.validate_comment(c) == "Field 'Kind' must not be specified"


def test_validate_comment_operation_must_not_be_specified() -> None:
    c = Comment()
    c.description = "myDesc"
    c.operation = "myOp"
    store, _ = _store(AsyncMock())
    assert store.validate_comment(c) == "Field 'Operation' must not be specified"


def test_validate_comment_description_required() -> None:
    c = Comment()
    store, _ = _store(AsyncMock())
    assert store.validate_comment(c) == "description is too short (0/1)"


# ---------------------------------------------------------------------------
# create_comment
# ---------------------------------------------------------------------------


async def test_create_comment_unexpected_id() -> None:
    store, _ = _store(AsyncMock())
    c = Comment()
    c.id = "123444"
    c.description = "myDesc"
    with pytest.raises(Exception, match="Unexpected ID found in new comment"):
        await store.create_comment(c)


async def test_create_comment_missing_case_id() -> None:
    store, _ = _store(AsyncMock())
    c = Comment()
    c.description = "myDesc"
    with pytest.raises(Exception, match="Missing Case ID in new comment"):
        await store.create_comment(c)


async def test_create_comment_indexes_then_reads_back() -> None:
    es = AsyncMock()
    es.index.return_value = {"_id": "myCommentId", "result": "created"}
    store, evs = _store(es)
    # 1st search: GetCase existence check. 2nd: read-back of the new comment.
    evs.queue(_rec("case", "123444"))
    evs.queue(_rec("comment", "myCommentId", **{"so_comment.caseId": "123444"}))
    c = Comment()
    c.case_id = "123444"
    c.description = "Foo Bar"
    created = await store.create_comment(c)
    assert created is not None
    assert created.id == "myCommentId"
    assert es.index.await_count == 2  # live + audit
    assert es.index.await_args_list[1].kwargs["document"]["so_operation"] == "create"


# ---------------------------------------------------------------------------
# get_comment / get_comments (Lucene query strings)
# ---------------------------------------------------------------------------


async def test_get_comment_builds_lucene_query() -> None:
    es = AsyncMock()
    store, evs = _store(es)
    evs.queue(_rec("comment", "myCommentId"))
    obj = await store.get_comment("myCommentId")
    assert obj is not None
    assert (
        evs.input_criterias[0].raw_query
        == '_index:"myIndex" AND so_kind:"comment" AND _id:"myCommentId"'
    )


async def test_get_comments_builds_sortby_query() -> None:
    es = AsyncMock()
    store, evs = _store(es)
    evs.queue(_rec("comment", "c1", **{"so_comment.caseId": "myCaseId"}))
    comments = await store.get_comments("myCaseId")
    assert len(comments) == 1
    assert (
        evs.input_criterias[0].raw_query
        == '_index:"myIndex" AND so_kind:"comment" AND so_comment.caseId:"myCaseId"'
        " | sortby so_comment.createTime^"
    )


# ---------------------------------------------------------------------------
# update_comment / delete_comment
# ---------------------------------------------------------------------------


async def test_update_comment_missing_id() -> None:
    store, _ = _store(AsyncMock())
    c = Comment()
    c.description = "myDesc"
    with pytest.raises(Exception, match="Missing comment ID"):
        await store.update_comment(c)


async def test_update_comment_preserves_create_time() -> None:
    es = AsyncMock()
    es.index.return_value = {"_id": "myCommentId", "result": "updated"}
    store, evs = _store(es)
    old_ct = datetime(2020, 1, 2, 3, 4, 5, tzinfo=UTC)
    # 1st search: GetComment(old). 2nd: read-back after save.
    evs.queue(_rec("comment", "myCommentId", **{"so_comment.createTime": old_ct}))
    evs.queue(_rec("comment", "myCommentId"))
    c = Comment()
    c.id = "myCommentId"
    c.description = "updated"
    await store.update_comment(c)
    # The saved live document carries the preserved (old) create time.
    live_doc = es.index.await_args_list[0].kwargs["document"]
    assert live_doc["so_comment"]["createTime"] == old_ct
    assert es.index.await_args_list[1].kwargs["document"]["so_operation"] == "update"


async def test_delete_comment_deletes_then_audits() -> None:
    es = AsyncMock()
    es.delete.return_value = {"_id": "myCommentId", "result": "deleted"}
    es.index.return_value = {"_id": "audit1", "result": "created"}
    store, evs = _store(es)
    evs.queue(_rec("comment", "myCommentId"))
    await store.delete_comment("myCommentId")
    assert (
        evs.input_criterias[0].raw_query
        == '_index:"myIndex" AND so_kind:"comment" AND _id:"myCommentId"'
    )
    assert es.delete.await_count == 1
    assert es.delete.await_args.kwargs["id"] == "myCommentId"
    assert es.delete.await_args.kwargs["index"] == "myIndex"
    # The delete audit doc is indexed with operation=delete.
    assert es.index.await_args_list[0].kwargs["document"]["so_operation"] == "delete"
