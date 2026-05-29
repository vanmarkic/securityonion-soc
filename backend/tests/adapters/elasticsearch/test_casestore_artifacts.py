"""ElasticCasestore artifact + artifact-stream unit tests (mocked client).

Ports the artifact side of ``server/modules/elastic/elasticcasestore.go``
(``validateArtifact``/``validateArtifactStream``, ``CreateArtifact``/
``GetArtifact``/``GetArtifacts``/``UpdateArtifact``/``DeleteArtifact``,
``CreateArtifactStream``/``GetArtifactStream``/``DeleteArtifactStream``,
``GetCaseIdsWithArtifact``) and the byte-pinned assertions from
``elasticcasestore_test.go``:

- the ``validateArtifact`` check order (value before groupType, so a bare
  artifact reports ``"value is too short (0/1)"`` then ``"invalid ID for
  groupType"``);
- ``UpdateArtifact`` preserving the many immutable fields (only Description /
  Tlp / Tags / Ioc / Protected are mutable);
- the ``GetArtifacts`` sortby query with the optional groupId term;
- ``CreateArtifactStream`` returning the document id directly (no read-back);
- ``GetCaseIdsWithArtifact`` free-text escaping + unique first-seen ordering;
  and ``DeleteArtifact`` cascading to the stream.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.adapters.elasticsearch.casestore import ElasticCasestore
from src.adapters.elasticsearch.client import ElasticClients
from src.adapters.elasticsearch.config import ElasticConfig
from src.adapters.elasticsearch.eventstore import ElasticEventstore
from src.domain.case import Artifact, ArtifactStream
from src.domain.event import EventRecord, EventSearchCriteria, EventSearchResults

_CFG = ElasticConfig(
    case_index="myIndex",
    audit_index="myAuditIndex",
    max_case_associations=45,
    schema_prefix="so_",
)


class _ScriptedEventstore(ElasticEventstore):
    """Eventstore returning queued results in order (Go's FakeEventstore)."""

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
# validate_artifact — check ordering (value before groupType)
# ---------------------------------------------------------------------------


def test_validate_artifact_missing_value_first() -> None:
    a = Artifact()
    a.group_type = "myGroupType"
    a.case_id = "12345"
    store, _ = _store(AsyncMock())
    assert store.validate_artifact(a) == "value is too short (0/1)"


def test_validate_artifact_missing_group_type() -> None:
    a = Artifact()
    a.value = "myValue"
    store, _ = _store(AsyncMock())
    assert store.validate_artifact(a) == "invalid ID for groupType"


def test_validate_artifact_missing_artifact_type() -> None:
    a = Artifact()
    a.group_type = "myGroupType"
    a.case_id = "12345"
    a.value = "myValue"
    store, _ = _store(AsyncMock())
    assert store.validate_artifact(a) == "artifactType is too short (0/1)"


# ---------------------------------------------------------------------------
# create_artifact
# ---------------------------------------------------------------------------


async def test_create_artifact_unexpected_id() -> None:
    a = Artifact()
    a.id = "123444"
    a.group_type = "myGroupType"
    a.artifact_type = "myArtifactType"
    a.value = "Value"
    store, _ = _store(AsyncMock())
    with pytest.raises(Exception, match="Unexpected ID found in new artifact"):
        await store.create_artifact(a)


async def test_create_artifact_missing_case_id() -> None:
    a = Artifact()
    a.group_type = "myGroupType"
    a.artifact_type = "myArtifactType"
    a.value = "Value"
    store, _ = _store(AsyncMock())
    with pytest.raises(Exception, match="Missing Case ID in new artifact"):
        await store.create_artifact(a)


async def test_create_artifact_indexes_then_reads_back() -> None:
    es = AsyncMock()
    es.index.return_value = {"_id": "myArtifactId", "result": "created"}
    store, evs = _store(es)
    evs.queue(_rec("case", "123444"))  # GetCase
    evs.queue(_rec("artifact", "myArtifactId"))  # read-back
    a = Artifact()
    a.case_id = "123444"
    a.group_type = "myGroupType"
    a.artifact_type = "myArtifactType"
    a.value = "Value"
    a.protected = True
    created = await store.create_artifact(a)
    assert created is not None
    assert created.id == "myArtifactId"
    assert es.index.await_count == 2  # live + audit


# ---------------------------------------------------------------------------
# get_artifact / get_artifacts (Lucene query strings)
# ---------------------------------------------------------------------------


async def test_get_artifact_builds_lucene_query() -> None:
    es = AsyncMock()
    store, evs = _store(es)
    evs.queue(_rec("artifact", "myArtifactId"))
    obj = await store.get_artifact("myArtifactId")
    assert obj is not None
    assert (
        evs.input_criterias[0].raw_query
        == '_index:"myIndex" AND so_kind:"artifact" AND _id:"myArtifactId"'
    )


async def test_get_artifacts_bad_group_type() -> None:
    store, _ = _store(AsyncMock())
    with pytest.raises(Exception, match="invalid ID for groupType"):
        await store.get_artifacts("myCaseId", "myGroupType is invalid", "myGroupId")


async def test_get_artifacts_bad_group_id() -> None:
    store, _ = _store(AsyncMock())
    with pytest.raises(Exception, match="invalid ID for groupId"):
        await store.get_artifacts("myCaseId", "myGroupType", "myGroupId is invalid")


async def test_get_artifacts_no_group_id_query() -> None:
    es = AsyncMock()
    store, evs = _store(es)
    evs.queue(_rec("artifact", "a1"))
    await store.get_artifacts("myCaseId", "myGroupType", "")
    assert evs.input_criterias[0].raw_query == (
        '_index:"myIndex" AND so_kind:"artifact" AND so_artifact.caseId:"myCaseId"'
        ' AND so_artifact.groupType:"myGroupType" | sortby so_artifact.createTime^'
    )


async def test_get_artifacts_with_group_id_query() -> None:
    es = AsyncMock()
    store, evs = _store(es)
    evs.queue(_rec("artifact", "a1"))
    await store.get_artifacts("myCaseId", "myGroupType", "myGroupId")
    assert evs.input_criterias[0].raw_query == (
        '_index:"myIndex" AND so_kind:"artifact" AND so_artifact.caseId:"myCaseId"'
        ' AND so_artifact.groupType:"myGroupType" AND so_artifact.groupId:"myGroupId"'
        " | sortby so_artifact.createTime^"
    )


# ---------------------------------------------------------------------------
# update_artifact — immutable-field preservation
# ---------------------------------------------------------------------------


async def test_update_artifact_missing_id() -> None:
    # Fields must pass validate_artifact so the missing-id check is reached
    # (Go's TestUpdateArtifact uses a valid artifact with no Id first).
    a = Artifact()
    a.value = "myValue"
    a.group_type = "myGroupType"
    a.artifact_type = "file"
    store, _ = _store(AsyncMock())
    with pytest.raises(Exception, match="Missing artifact ID"):
        await store.update_artifact(a)


async def test_update_artifact_preserves_immutable_fields() -> None:
    es = AsyncMock()
    es.index.return_value = {"_id": "myArtifactId", "result": "updated"}
    store, evs = _store(es)
    old = _rec(
        "artifact",
        "myArtifactId",
        **{
            "so_artifact.artifactType": "myArtifactType",
            "so_artifact.groupType": "myGroupType",
            "so_artifact.groupId": "myGroupId",
            "so_artifact.value": "myValue",
            "so_artifact.streamLength": 123.0,
            "so_artifact.mimeType": "myMimeType",
            "so_artifact.md5": "myMd5",
            "so_artifact.sha1": "mySha1",
            "so_artifact.sha256": "mySha256",
            "so_artifact.streamId": "myStreamId",
            "so_artifact.description": "myDesc",
        },
    )
    evs.queue(old)  # GetArtifact(old)
    evs.queue(_rec("artifact", "myArtifactId"))  # read-back
    a = Artifact()
    a.id = "myArtifactId"
    a.value = "myNewValue"
    a.group_type = "myNewGroupType"
    a.group_id = "myNewGroupId"
    a.artifact_type = "file"
    a.mime_type = "myNewMimeType"
    a.md5 = "myNewMd5"
    a.sha1 = "myNewSha1"
    a.sha256 = "myNewSha256"
    a.stream_id = "myNewStreamId"
    a.stream_len = 456
    a.description = "myNewDesc"
    await store.update_artifact(a)
    live_doc = es.index.await_args_list[0].kwargs["document"]
    assert live_doc["so_operation"] == "update"
    saved = live_doc["so_artifact"]
    assert saved["description"] == "myNewDesc"  # mutable
    # Immutable fields preserved from the old artifact.
    assert saved["artifactType"] == "myArtifactType"
    assert saved["groupType"] == "myGroupType"
    assert saved["groupId"] == "myGroupId"
    assert saved["streamId"] == "myStreamId"
    assert saved["mimeType"] == "myMimeType"
    assert saved["md5"] == "myMd5"
    assert saved["sha1"] == "mySha1"
    assert saved["sha256"] == "mySha256"
    assert saved["value"] == "myValue"
    assert saved["streamLength"] == 123


# ---------------------------------------------------------------------------
# delete_artifact (cascade to stream + analyzer-job hook no-op)
# ---------------------------------------------------------------------------


async def test_delete_artifact_cascades_stream() -> None:
    es = AsyncMock()
    es.delete.return_value = {"_id": "x", "result": "deleted"}
    es.index.return_value = {"_id": "audit1", "result": "created"}
    store, evs = _store(es)
    # GetArtifact returns one carrying a streamId, then GetArtifactStream.
    evs.queue(_rec("artifact", "myArtifactId", **{"so_artifact.streamId": "myStreamId"}))
    evs.queue(_rec("artifactstream", "myStreamId"))
    await store.delete_artifact("myArtifactId")
    deleted_ids = [c.kwargs["id"] for c in es.delete.await_args_list]
    assert "myStreamId" in deleted_ids  # stream cascade
    assert "myArtifactId" in deleted_ids  # artifact itself


# ---------------------------------------------------------------------------
# artifact streams
# ---------------------------------------------------------------------------


def test_validate_artifact_stream_missing_content() -> None:
    s = ArtifactStream()
    store, _ = _store(AsyncMock())
    assert store.validate_artifact_stream(s) == "Missing stream content"


async def test_create_artifact_stream_unexpected_id() -> None:
    s = ArtifactStream()
    s.id = "123444"
    s.content = "Value"
    store, _ = _store(AsyncMock())
    with pytest.raises(Exception, match="Unexpected ID found in new artifactstream"):
        await store.create_artifact_stream(s)


async def test_create_artifact_stream_returns_id_no_readback() -> None:
    es = AsyncMock()
    es.index.return_value = {"_id": "myArtifactStreamId", "result": "created"}
    store, evs = _store(es)
    s = ArtifactStream()
    s.content = "Content"
    stream_id = await store.create_artifact_stream(s)
    assert stream_id == "myArtifactStreamId"
    # No read-back search — only the live + audit index calls.
    assert evs.input_criterias == []
    assert es.index.await_count == 2


async def test_get_artifact_stream_bad_id() -> None:
    store, _ = _store(AsyncMock())
    with pytest.raises(Exception, match="invalid ID for artifactStreamId"):
        await store.get_artifact_stream("stream id is invalid")


# ---------------------------------------------------------------------------
# get_case_ids_with_artifact (escaping + unique first-seen order)
# ---------------------------------------------------------------------------


async def test_get_case_ids_with_artifact_unique_order() -> None:
    es = AsyncMock()
    store, evs = _store(es)
    evs.queue(
        _rec("artifact", **{"so_artifact.caseId": "case1"}),
        _rec("artifact", **{"so_artifact.caseId": "case2"}),
        _rec("artifact", **{"so_artifact.caseId": "case1"}),  # duplicate
    )
    case_ids = await store.get_case_ids_with_artifact(
        "assistant_session", "chat_1764962755081_dl2dzsuq6",
    )
    assert evs.input_criterias[0].raw_query == (
        '_index:"myIndex" AND so_kind:"artifact" AND'
        ' so_artifact.artifactType:"assistant_session" AND'
        ' so_artifact.value:"chat_1764962755081_dl2dzsuq6"'
    )
    assert case_ids == ["case1", "case2"]  # unique, first-seen order


async def test_get_case_ids_with_artifact_invalid_params() -> None:
    store, _ = _store(AsyncMock())
    with pytest.raises(Exception, match="artType"):
        await store.get_case_ids_with_artifact("", "192.168.1.1")
    with pytest.raises(Exception, match="value"):
        await store.get_case_ids_with_artifact("ip", "")


async def test_get_case_ids_with_artifact_escapes_injection() -> None:
    es = AsyncMock()
    store, evs = _store(es)
    evs.queue()
    attack = 'myValue" OR so_artifact.value:"otherValue'
    await store.get_case_ids_with_artifact("ip", attack)
    query = evs.input_criterias[0].raw_query
    assert (
        'so_artifact.value:"myValue\\" OR so_artifact.value:\\"otherValue"' in query
    )
