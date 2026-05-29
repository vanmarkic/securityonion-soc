"""ElasticCasestore related-event unit tests (mocked AsyncElasticsearch).

Ports the related-event side of ``server/modules/elastic/elasticcasestore.go``
(``validateRelatedEvent``, ``CreateRelatedEvents``, ``GetRelatedEvent``/
``GetRelatedEvents``/``DeleteRelatedEvent``, ``ExtractCommonObservables``) and the
byte-pinned assertions from ``elasticcasestore_test.go``:

- ``CreateRelatedEvents`` returns ``(total_created, err_map, fatal)``;
- the per-event errors ``"Unexpected ID found in new related event"``,
  ``"Missing Case ID in new related event"``, the preserved-typo
  ``"Related event fields cannot not be empty"``, and the duplicate sentinel
  ``"ERROR_CASE_EVENT_ALREADY_ATTACHED"`` keyed by ``soc_id``;
- the manual in-memory sort of ``GetRelatedEvents`` by ``fields["timestamp"]``
  with missing-timestamp-first; and
- the ``ip`` observable extracted for a ``commonObservables`` field.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

from src.adapters.elasticsearch.casestore import ElasticCasestore
from src.adapters.elasticsearch.client import ElasticClients
from src.adapters.elasticsearch.config import ElasticConfig
from src.adapters.elasticsearch.eventstore import ElasticEventstore
from src.domain.case import RelatedEvent
from src.domain.event import EventRecord, EventSearchCriteria, EventSearchResults

_CFG = ElasticConfig(
    case_index="myIndex",
    audit_index="myAuditIndex",
    max_case_associations=45,
    schema_prefix="so_",
    extract_common_observables=["source.ip", "destination.ip"],
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


def _store(
    es: AsyncMock, cfg: ElasticConfig = _CFG,
) -> tuple[ElasticCasestore, _ScriptedEventstore]:
    eventstore = _ScriptedEventstore(
        ElasticClients(primary=es), cfg, requestor_id="myRequestorId",
    )
    store = ElasticCasestore(
        ElasticClients(primary=es), cfg, requestor_id="myRequestorId",
        eventstore=eventstore,
    )
    return store, eventstore


def _rec(kind: str, doc_id: str = "", **fields: object) -> EventRecord:
    rec = EventRecord()
    rec.id = doc_id
    rec.payload = {"so_kind": kind, **fields}
    return rec


# ---------------------------------------------------------------------------
# validate_related_event — exact error strings
# ---------------------------------------------------------------------------


def test_validate_related_event_missing_fields() -> None:
    # Preserve Go's grammatical typo verbatim.
    store, _ = _store(AsyncMock())
    assert (
        store.validate_related_event(RelatedEvent())
        == "Related event fields cannot not be empty"
    )


# ---------------------------------------------------------------------------
# create_related_events — per-event errors keyed by soc_id
# ---------------------------------------------------------------------------


async def test_create_related_events_unexpected_id() -> None:
    store, _ = _store(AsyncMock())
    ev = RelatedEvent()
    ev.id = "123444"
    ev.fields = {"foo": "bar", "soc_id": "soc_id"}
    total, err_map, fatal = await store.create_related_events([ev])
    assert fatal is None
    assert total == 0
    assert err_map == {"soc_id": "Unexpected ID found in new related event"}


async def test_create_related_events_missing_case_id() -> None:
    store, _ = _store(AsyncMock())
    ev = RelatedEvent()
    ev.fields = {"foo": "bar", "soc_id": "soc_id"}
    total, err_map, fatal = await store.create_related_events([ev])
    assert fatal is None
    assert total == 0
    assert err_map["soc_id"] == "Missing Case ID in new related event"


async def test_create_related_events_missing_fields() -> None:
    store, _ = _store(AsyncMock())
    total, err_map, fatal = await store.create_related_events([RelatedEvent()])
    assert fatal is None
    assert total == 0
    assert err_map[""] == "Related event fields cannot not be empty"


async def test_create_related_events_already_attached() -> None:
    es = AsyncMock()
    store, evs = _store(es)
    # GetCase exists, then GetRelatedEvents returns one with matching soc_id.
    evs.queue(_rec("case", "123444"))
    evs.queue(_rec("related", **{"so_related.fields.soc_id": "myEventId"}))
    # GetArtifacts (observable extraction) — no existing artifacts.
    evs.queue()
    ev = RelatedEvent()
    ev.case_id = "123444"
    ev.fields = {"soc_id": "myEventId"}
    total, err_map, fatal = await store.create_related_events([ev])
    assert fatal is None
    assert total == 0
    assert err_map == {"myEventId": "ERROR_CASE_EVENT_ALREADY_ATTACHED"}


async def test_create_related_events_creates_and_extracts_observable() -> None:
    es = AsyncMock()
    es.index.return_value = {"_id": "REL1", "result": "created"}
    store, evs = _store(es)
    # Search order: GetCase (create_related_events), GetRelatedEvents (empty),
    # GetArtifacts (existing-values, empty), then inside CreateArtifact a
    # GetCase existence check followed by the new-artifact read-back.
    evs.queue(_rec("case", "123444"))
    evs.queue()
    evs.queue()
    evs.queue(_rec("case", "123444"))
    evs.queue(_rec("artifact", "ART1"))
    ev = RelatedEvent()
    ev.case_id = "123444"
    ev.fields = {"soc_id": "soc_id", "foo": "bar", "source.ip": "127.0.0.1"}
    total, err_map, fatal = await store.create_related_events([ev])
    assert fatal is None
    assert err_map == {}
    assert total == 1
    # The extracted artifact is an IP observable in the evidence group.
    artifact_docs = [
        call.kwargs["document"]
        for call in es.index.await_args_list
        if "so_artifact" in call.kwargs["document"]
    ]
    assert artifact_docs, "expected an artifact to be indexed"
    art = artifact_docs[0]["so_artifact"]
    assert art["groupType"] == "evidence"
    assert art["value"] == "127.0.0.1"
    assert art["artifactType"] == "ip"


async def test_create_related_events_caps_per_case_at_max_bulk_escalate() -> None:
    """Port of Go's MaxBulkEscalateEvents per-case cap (elasticcasestore.go:489,511).

    Go caps the per-case grouping at ClientParams.AlertingParams.MaxBulkEscalateEvents
    — a config value distinct from maxAssociations (the Go test sets it to 100 while
    maxAssociations defaults to 1000). The cap must come from
    max_bulk_escalate_events, NOT max_case_associations, so set them to different
    values and assert the bulk cap (2), not the association cap (45), is honored.
    """
    es = AsyncMock()
    es.index.return_value = {"_id": "REL", "result": "created"}
    cfg = _CFG.model_copy(
        update={"max_bulk_escalate_events": 2, "extract_common_observables": []},
    )
    store, evs = _store(es, cfg)
    # GetCase exists, then GetRelatedEvents empty. Observable extraction is a
    # no-op (extract_common_observables=[]), so no further searches consumed.
    evs.queue(_rec("case", "123444"))
    evs.queue()
    events = []
    for i in range(5):
        ev = RelatedEvent()
        ev.case_id = "123444"
        ev.fields = {"soc_id": f"id{i}"}
        events.append(ev)
    total, err_map, fatal = await store.create_related_events(events)
    assert fatal is None
    assert err_map == {}
    # Only the first 2 events (max_bulk_escalate_events) are grouped and created;
    # the other 3 are dropped at grouping time (45 = max_case_associations would
    # have created all 5).
    assert total == 2


# ---------------------------------------------------------------------------
# get_related_event / get_related_events (query + manual sort)
# ---------------------------------------------------------------------------


async def test_get_related_event_builds_lucene_query() -> None:
    es = AsyncMock()
    store, evs = _store(es)
    evs.queue(_rec("related", "myEventId"))
    obj = await store.get_related_event("myEventId")
    assert obj is not None
    assert (
        evs.input_criterias[0].raw_query
        == '_index:"myIndex" AND so_kind:"related" AND _id:"myEventId"'
    )


async def test_get_related_events_manual_sort() -> None:
    es = AsyncMock()
    store, evs = _store(es)
    time_a = datetime(2006, 1, 2, 15, 4, 5, tzinfo=UTC)
    time_b = datetime(2006, 1, 1, 15, 4, 5, tzinfo=UTC)
    evs.queue(
        _rec("related"),  # no timestamp -> sorts first
        _rec("related", **{"so_related.fields.timestamp": time_a}),
        _rec("related", **{"so_related.fields.timestamp": time_b}),
    )
    events = await store.get_related_events("myCaseId")
    assert (
        evs.input_criterias[0].raw_query
        == '_index:"myIndex" AND so_kind:"related" AND so_related.caseId:"myCaseId"'
    )
    assert len(events) == 3
    assert events[0].fields.get("timestamp") is None
    assert events[1].fields["timestamp"] == time_b
    assert events[2].fields["timestamp"] == time_a


async def test_delete_related_event_deletes_then_audits() -> None:
    es = AsyncMock()
    es.delete.return_value = {"_id": "myEventId", "result": "deleted"}
    es.index.return_value = {"_id": "audit1", "result": "created"}
    store, evs = _store(es)
    evs.queue(_rec("related", "myEventId"))
    await store.delete_related_event("myEventId")
    assert es.delete.await_count == 1
    assert es.delete.await_args.kwargs["id"] == "myEventId"
    assert es.index.await_args_list[0].kwargs["document"]["so_operation"] == "delete"


# ---------------------------------------------------------------------------
# extract_common_observables (returns error variant)
# ---------------------------------------------------------------------------


async def test_extract_common_observables_nothing_to_extract() -> None:
    cfg = _CFG.model_copy(update={"extract_common_observables": ["my IP addr"]})
    store, evs = _store(AsyncMock(), cfg)
    evs.queue()  # GetArtifacts: no existing artifacts
    ev = RelatedEvent()
    ev.case_id = "testID"
    assert await store.extract_common_observables(ev) is None


async def test_extract_common_observables_skip_empty_value() -> None:
    cfg = _CFG.model_copy(update={"extract_common_observables": ["my IP addr"]})
    store, evs = _store(AsyncMock(), cfg)
    evs.queue()  # GetArtifacts
    ev = RelatedEvent()
    ev.case_id = "testID"
    ev.fields = {"my IP addr": ""}
    assert await store.extract_common_observables(ev) is None


async def test_extract_common_observables_skip_when_exists() -> None:
    cfg = _CFG.model_copy(update={"extract_common_observables": ["my IP addr"]})
    es = AsyncMock()
    store, evs = _store(es, cfg)
    evs.queue(_rec("artifact", **{"so_artifact.value": "127.0.0.1"}))
    ev = RelatedEvent()
    ev.case_id = "testID"
    ev.fields = {"my IP addr": "127.0.0.1"}
    assert await store.extract_common_observables(ev) is None
    # Nothing new indexed since the value already exists.
    assert es.index.await_count == 0
