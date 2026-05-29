"""ElasticCasestore — ES-backed implementation of the Casestore port.

Ports the case-side of ``server/modules/elastic/elasticcasestore.go``
(``validateCase``, ``prepareForSave``, ``save``/``get``/``getAll``,
``Create``/``Update``/``GetCase``/``GetCaseHistory``).

The store builds a ``{<prefix>case: <case>, <prefix>kind: "case", '@timestamp':
now}`` document, indexes it with ``refresh="true"`` (read-after-write), and
writes an audit snapshot — all via the shared ``store_base`` (Task 13). Reads go
through a composed :class:`ElasticEventstore`, mirroring Go's
``store.server.Eventstore.Search``: a Lucene query string
(``_index:"<index>" AND <prefix>kind:"<kind>" AND _id:"<escaped id>"``) is run
through the same field-caps + ``make_query`` pipeline and each hit is mapped back
to a domain object via ``convert_elastic_event_to_object``.

Divergence from Go: the Python ``Casestore`` port (``src/ports/cases.py``) takes
no ``ctx`` argument and performs no ``server.CheckAuthorized`` — authorization
happens at the FastAPI route/dependency layer — so the Go ``CheckAuthorized``
calls are dropped. The requestor id (Go ``web.ContextKeyRequestorId``) is
supplied to the constructor as ``requestor_id`` and stamped onto each saved
object's ``userId`` in ``_prepare_for_save``.

Task 14 implemented the case CRUD + history methods. Task 15 adds the remaining
``Casestore`` protocol methods: comments (15a, with the observables classifier),
related events (15b, bulk create + manual sort + observable extraction), and
artifacts + artifact streams (15c).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from src.adapters.elasticsearch.client import ElasticClients
from src.adapters.elasticsearch.config import ElasticConfig
from src.adapters.elasticsearch.converter import (
    convert_elastic_event_to_object,
    convert_object_to_document_map,
    convert_severity,
)
from src.adapters.elasticsearch.escaping import escape_lucene, validate_id
from src.adapters.elasticsearch.eventstore import ElasticEventstore
from src.adapters.elasticsearch.helpers import (
    LONG_STRING_MAX,
    MAX_ARRAY_ELEMENTS,
    SHORT_STRING_MAX,
    validate_string,
    validate_string_array,
    validate_string_required,
)
from src.adapters.elasticsearch.observables import Observables
from src.adapters.elasticsearch.store_base import (
    delete_with_audit,
    save_with_audit,
)
from src.domain.case import (
    Artifact,
    ArtifactStream,
    Auditable,
    Case,
    Comment,
    RelatedEvent,
)
from src.domain.event import EventSearchCriteria

logger = logging.getLogger(__name__)

# Go: artifact observable extraction always groups under "evidence".
_EVIDENCE_GROUP = "evidence"

# Go: model.CASE_STATUS_NEW (model/case.go:23).
CASE_STATUS_NEW = "new"

# Go getAll uses this date layout for the now-anchored timeframe (Go
# "2006-01-02 3:04:05 PM").
_GETALL_DATE_FORMAT = "%Y-%m-%d %I:%M:%S %p"


class ElasticCasestore:
    """Casestore port backed by one or more ``AsyncElasticsearch`` clients."""

    def __init__(
        self,
        clients: ElasticClients,
        config: ElasticConfig,
        requestor_id: str = "",
        *,
        eventstore: ElasticEventstore | None = None,
    ) -> None:
        self._clients = clients
        self._config = config
        self._requestor_id = requestor_id
        self._observables = Observables()
        # Compose an eventstore for the read/search path (Go's
        # store.server.Eventstore.Search). Tests may inject a recording double.
        self._eventstore = eventstore or ElasticEventstore(
            clients, config, requestor_id,
        )

    @property
    def _index(self) -> str:
        return self._config.case_index

    @property
    def _audit_index(self) -> str:
        return self._config.audit_index

    @property
    def _prefix(self) -> str:
        return self._config.schema_prefix

    # ------------------------------------------------------------------
    # validation (Go validateCase)
    # ------------------------------------------------------------------

    def validate_case(self, case: Case) -> str | None:
        """Port of ``validateCase`` (elasticcasestore.go:116).

        Mutates ``case.severity`` via ``convertSeverity`` (matching Go) and
        returns the first validation error string, or ``None`` when valid. The
        check order matches Go exactly so the pinned error strings line up.
        """
        if case.id != "":
            err = validate_id(case.id, "caseId")
            if err:
                return err
        if case.user_id != "":
            err = validate_id(case.user_id, "userId")
            if err:
                return err
        if case.assignee_id != "":
            err = validate_id(case.assignee_id, "assigneeId")
            if err:
                return err
        if case.priority < 0:
            return "Invalid priority"
        case.severity = convert_severity(case.severity)
        err = validate_string(case.severity, SHORT_STRING_MAX, "severity")
        if err:
            return err
        if case.kind:
            return "Field 'Kind' must not be specified"
        if case.operation:
            return "Field 'Operation' must not be specified"
        err = validate_string_required(case.title, 1, SHORT_STRING_MAX, "title")
        if err:
            return err
        err = validate_string(case.category, SHORT_STRING_MAX, "category")
        if err:
            return err
        err = validate_string_required(case.status, 1, SHORT_STRING_MAX, "status")
        if err:
            return err
        err = validate_string(case.template, SHORT_STRING_MAX, "template")
        if err:
            return err
        err = validate_string(case.tlp, SHORT_STRING_MAX, "tlp")
        if err:
            return err
        err = validate_string(case.pap, SHORT_STRING_MAX, "pap")
        if err:
            return err
        err = validate_string_required(
            case.description, 1, LONG_STRING_MAX, "description",
        )
        if err:
            return err
        return validate_string_array(
            case.tags, SHORT_STRING_MAX, MAX_ARRAY_ELEMENTS, "tags",
        )

    # ------------------------------------------------------------------
    # save / get / get_all (Go save/get/getAll)
    # ------------------------------------------------------------------

    def _prepare_for_save(self, obj: Auditable) -> str:
        """Port of ``prepareForSave`` (elasticcasestore.go:294).

        Stamps the requestor id, then strips the ``id``/``update_time`` from the
        document (ES already stores them) and returns the original id so the
        caller knows whether this is a create (``""``) or update. Accepts any
        ``Auditable`` (case/comment/related/artifact/artifactstream).
        """
        obj.user_id = self._requestor_id
        doc_id = obj.id
        obj.id = ""
        obj.update_time = None
        return doc_id

    async def _save(self, obj: Auditable, kind: str, doc_id: str) -> str:
        """Port of ``save`` (elasticcasestore.go:305) for any auditable object.

        Indexes the live document then the audit snapshot via the shared base,
        and returns the live document id.
        """
        document = convert_object_to_document_map(
            kind, obj.model_dump(by_alias=True), self._prefix,
        )
        document[self._prefix + "kind"] = kind
        result = await save_with_audit(
            self._clients.read_client,
            index=self._index,
            audit_index=self._audit_index,
            document=document,
            doc_id=doc_id,
            prefix=self._prefix,
        )
        return result.document_id

    async def _delete(self, obj: Auditable, kind: str, doc_id: str) -> None:
        """Port of ``delete`` (elasticcasestore.go:332) for any auditable object.

        Deletes the live document then writes a ``delete`` audit snapshot via the
        shared base.
        """
        document = convert_object_to_document_map(
            kind, obj.model_dump(by_alias=True), self._prefix,
        )
        document[self._prefix + "kind"] = kind
        await delete_with_audit(
            self._clients.read_client,
            index=self._index,
            audit_index=self._audit_index,
            document=document,
            doc_id=doc_id,
            prefix=self._prefix,
        )

    async def _get(self, doc_id: str, kind: str) -> Any:
        """Port of ``get`` (elasticcasestore.go:355).

        Builds the by-id Lucene query, runs ``_get_all`` with a limit of 1, and
        raises ``"Object not found"`` when no object matches.
        """
        query = (
            f'_index:"{self._index}" AND {self._prefix}kind:"{escape_lucene(kind)}" '
            f'AND _id:"{escape_lucene(doc_id)}"'
        )
        objects = await self._get_all(query, 1)
        if objects:
            return objects[0]
        raise RuntimeError("Object not found")

    async def _get_all(self, query: str, limit: int) -> list[Any]:
        """Port of ``getAll`` (elasticcasestore.go:367).

        Populates an ``EventSearchCriteria`` exactly as Go does (now-anchored
        timeframe, no metrics, ``limit`` events), runs the composed eventstore's
        ``search``, and maps each hit to a domain object. Conversion failures are
        skipped (Go logs and continues).
        """
        criteria = EventSearchCriteria()
        now = datetime.now(UTC)
        zero_time = datetime(1, 1, 1, tzinfo=UTC)
        timeframe = (
            f"{zero_time.strftime(_GETALL_DATE_FORMAT)} - "
            f"{now.strftime(_GETALL_DATE_FORMAT)}"
        )
        criteria.populate(
            query,
            timeframe,
            _GETALL_DATE_FORMAT,
            "UTC",
            "0",
            str(limit),
        )

        results = await self._eventstore.search(criteria)
        objects: list[Any] = []
        for event in results.events:
            obj, err = convert_elastic_event_to_object(event, self._prefix)
            if err is None and obj is not None:
                objects.append(obj)
        return objects

    # ------------------------------------------------------------------
    # public Casestore API (Go Create/Update/GetCase/GetCaseHistory)
    # ------------------------------------------------------------------

    async def create(self, case: Case) -> Case:
        """Port of ``Create`` (elasticcasestore.go:405).

        Forces the status to ``new``, validates, rejects a supplied id, stamps
        the create time, saves (live + audit), and reads the case back to pick up
        the server-assigned id/update time.
        """
        case.status = CASE_STATUS_NEW
        err = self.validate_case(case)
        if err:
            raise RuntimeError(err)
        if case.id != "":
            raise RuntimeError("Unexpected ID found in new case")
        # Templates are applied in a later task; with an empty template this is a
        # no-op (Go applyTemplate returns the case unchanged when Template == "").
        case.create_time = datetime.now(UTC)
        doc_id = await self._save(case, "case", self._prepare_for_save(case))
        return await self.get_case(doc_id) or case

    async def update(self, case: Case) -> Case:
        """Port of ``Update`` (elasticcasestore.go:428).

        Validates, requires an id, reads the existing case to preserve read-only
        times and run the status workflow, saves, then reads back.
        """
        err = self.validate_case(case)
        if err:
            raise RuntimeError(err)
        if case.id == "":
            raise RuntimeError("Missing case ID")
        old_case = await self.get_case(case.id)
        if old_case is not None:
            case.create_time = old_case.create_time
            case.complete_time = old_case.complete_time
            case.start_time = old_case.start_time
            case.process_workflow_for_status(old_case)
        doc_id = await self._save(case, "case", self._prepare_for_save(case))
        return await self.get_case(doc_id) or case

    async def get_case(self, case_id: str) -> Case | None:
        """Port of ``GetCase`` (elasticcasestore.go:456)."""
        err = validate_id(case_id, "caseId")
        if err:
            raise RuntimeError(err)
        obj = await self._get(case_id, "case")
        return obj if isinstance(obj, Case) else None

    async def get_case_history(self, case_id: str) -> list[Any]:
        """Port of ``GetCaseHistory`` (elasticcasestore.go:471).

        Searches the audit index for every audit/comment/related/artifact doc
        carrying this case id, ordered by ``@timestamp`` ascending.
        """
        err = validate_id(case_id, "caseId")
        if err:
            raise RuntimeError(err)
        escaped = escape_lucene(case_id)
        prefix = self._prefix
        query = (
            f'_index:"{self._audit_index}" AND ('
            f'{prefix}audit_doc_id:"{escaped}" OR '
            f'{prefix}comment.caseId:"{escaped}" OR '
            f'{prefix}related.caseId:"{escaped}" OR '
            f'{prefix}artifact.caseId:"{escaped}") | sortby @timestamp^'
        )
        return await self._get_all(query, self._config.max_case_associations)

    # ==================================================================
    # 15a — Comments (Go validateComment / Create/Get/GetComments/Update/Delete)
    # ==================================================================

    def validate_comment(self, comment: Comment) -> str | None:
        """Port of ``validateComment`` (elasticcasestore.go:192).

        Returns the first validation error string, or ``None``. The check order
        matches Go so the pinned error strings line up.
        """
        if comment.id != "":
            err = validate_id(comment.id, "commentId")
            if err:
                return err
        if comment.case_id != "":
            err = validate_id(comment.case_id, "caseId")
            if err:
                return err
        if comment.user_id != "":
            err = validate_id(comment.user_id, "userId")
            if err:
                return err
        if comment.kind:
            return "Field 'Kind' must not be specified"
        if comment.operation:
            return "Field 'Operation' must not be specified"
        return validate_string_required(
            comment.description, 1, LONG_STRING_MAX, "description",
        )

    async def create_comment(self, comment: Comment) -> Comment:
        """Port of ``CreateComment`` (elasticcasestore.go:791)."""
        err = self.validate_comment(comment)
        if err:
            raise RuntimeError(err)
        if comment.id != "":
            raise RuntimeError("Unexpected ID found in new comment")
        if comment.case_id == "":
            raise RuntimeError("Missing Case ID in new comment")
        await self.get_case(comment.case_id)  # confirm the case exists
        comment.create_time = datetime.now(UTC)
        doc_id = await self._save(comment, "comment", self._prepare_for_save(comment))
        return await self.get_comment(doc_id) or comment

    async def get_comment(self, comment_id: str) -> Comment | None:
        """Port of ``GetComment`` (elasticcasestore.go:817)."""
        err = validate_id(comment_id, "commentId")
        if err:
            raise RuntimeError(err)
        obj = await self._get(comment_id, "comment")
        return obj if isinstance(obj, Comment) else None

    async def get_comments(self, case_id: str) -> list[Comment]:
        """Port of ``GetComments`` (elasticcasestore.go:832)."""
        err = validate_id(case_id, "caseId")
        if err:
            raise RuntimeError(err)
        prefix = self._prefix
        query = (
            f'_index:"{self._index}" AND {prefix}kind:"comment" AND '
            f'{prefix}comment.caseId:"{escape_lucene(case_id)}" '
            f"| sortby {prefix}comment.createTime^"
        )
        objects = await self._get_all(query, self._config.max_case_associations)
        return [o for o in objects if isinstance(o, Comment)]

    async def update_comment(self, comment: Comment) -> Comment:
        """Port of ``UpdateComment`` (elasticcasestore.go:851)."""
        err = self.validate_comment(comment)
        if err:
            raise RuntimeError(err)
        if comment.id == "":
            raise RuntimeError("Missing comment ID")
        old = await self.get_comment(comment.id)
        if old is not None:
            comment.create_time = old.create_time  # preserve read-only field
        doc_id = await self._save(comment, "comment", self._prepare_for_save(comment))
        return await self.get_comment(doc_id) or comment

    async def delete_comment(self, comment_id: str) -> None:
        """Port of ``DeleteComment`` (elasticcasestore.go:876)."""
        comment = await self.get_comment(comment_id)
        if comment is not None:
            await self._delete(
                comment, "comment", self._prepare_for_save(comment),
            )

    # ==================================================================
    # 15b — Related events (Go CreateRelatedEvents / Get / Delete + extraction)
    # ==================================================================

    def validate_related_event(self, event: RelatedEvent) -> str | None:
        """Port of ``validateRelatedEvent`` (elasticcasestore.go:168)."""
        if event.id != "":
            err = validate_id(event.id, "relatedEventId")
            if err:
                return err
        if event.case_id != "":
            err = validate_id(event.case_id, "caseId")
            if err:
                return err
        if event.user_id != "":
            err = validate_id(event.user_id, "userId")
            if err:
                return err
        if event.kind:
            return "Field 'Kind' must not be specified"
        if event.operation:
            return "Field 'Operation' must not be specified"
        if not event.fields:
            # Preserve Go's grammatical typo verbatim.
            return "Related event fields cannot not be empty"
        return None

    async def create_related_events(
        self, events: list[RelatedEvent],
    ) -> tuple[int, dict[str, str], None | str]:
        """Port of ``CreateRelatedEvents`` (elasticcasestore.go:484).

        Validates and groups events by case (capped per-case at
        ``ElasticConfig.max_bulk_escalate_events`` — Go's
        ``MaxBulkEscalateEvents``, distinct from ``max_case_associations``),
        skips duplicates already attached to the case, indexes the remainder, then
        extracts common observables — swallowing extraction errors. Returns
        ``(total_created, err_map, fatal)`` where ``err_map`` is keyed by each
        event's ``soc_id``.

        Divergence from Go: the Go ``BulkIndexer`` two-phase fan-out is replaced
        by a serial awaited index loop (each live doc + audit snapshot via the
        shared ``save_with_audit``), which is sufficient and deterministic at the
        port's scale; ``fatal`` is therefore always ``None`` here.
        """
        err_map: dict[str, str] = {}
        total_created = 0
        # Go caps the per-case grouping at MaxBulkEscalateEvents
        # (elasticcasestore.go:489,511) — a config value distinct from
        # maxAssociations; see ElasticConfig.max_bulk_escalate_events.
        max_bulk = self._config.max_bulk_escalate_events
        events_by_case: dict[str, list[RelatedEvent]] = {}

        for event in events:
            event_id = self._soc_id(event)
            err = self.validate_related_event(event)
            if err is not None:
                err_map[event_id] = err
                continue
            if event.id != "":
                err_map[event_id] = "Unexpected ID found in new related event"
                continue
            if event.case_id == "":
                err_map[event_id] = "Missing Case ID in new related event"
                continue
            bucket = events_by_case.setdefault(event.case_id, [])
            if len(bucket) < max_bulk:
                bucket.append(event)

        for case_id, case_events in events_by_case.items():
            if not case_events:
                continue
            try:
                await self.get_case(case_id)  # does the case exist?
            except RuntimeError as exc:
                for event in case_events:
                    err_map[self._soc_id(event)] = str(exc)
                continue

            existing = await self.get_related_events(case_id)
            set_of_existing = {
                str(v)
                for ev in existing
                if (v := ev.fields.get("soc_id")) is not None
            }

            for event in case_events:
                event_id = self._soc_id(event)
                if event_id and event_id in set_of_existing:
                    err_map[event_id] = "ERROR_CASE_EVENT_ALREADY_ATTACHED"
                    continue
                await self._save(
                    event, "related", self._prepare_for_save(event),
                )
                total_created += 1

            # extract observables, don't error out if it fails
            await self._extract_observables(case_id, case_events)

        return total_created, err_map, None

    async def get_related_event(self, event_id: str) -> RelatedEvent | None:
        """Port of ``GetRelatedEvent`` (elasticcasestore.go:725)."""
        err = validate_id(event_id, "relatedEventId")
        if err:
            raise RuntimeError(err)
        obj = await self._get(event_id, "related")
        return obj if isinstance(obj, RelatedEvent) else None

    async def get_related_events(self, case_id: str) -> list[RelatedEvent]:
        """Port of ``GetRelatedEvents`` (elasticcasestore.go:740).

        The Go ``| sortby`` clause was removed in 2022 (ES 8.4 flattened-field
        sort incompatibility); the events are instead sorted in memory by their
        ``fields["timestamp"]`` ascending, with missing/untyped timestamps first
        (a stable, Go-faithful comparator).
        """
        err = validate_id(case_id, "caseId")
        if err:
            raise RuntimeError(err)
        prefix = self._prefix
        query = (
            f'_index:"{self._index}" AND {prefix}kind:"related" AND '
            f'{prefix}related.caseId:"{escape_lucene(case_id)}"'
        )
        objects = await self._get_all(query, self._config.max_case_associations)
        events = [o for o in objects if isinstance(o, RelatedEvent)]
        events.sort(key=self._timestamp_sort_key)
        return events

    @staticmethod
    def _timestamp_sort_key(event: RelatedEvent) -> tuple[int, datetime]:
        """Sort missing/untyped timestamps first, then by datetime ascending.

        Mirrors Go's ``sort.Slice`` comparator which returns ``false`` for any
        event lacking a ``time.Time`` timestamp, keeping such events ahead of the
        typed ones.
        """
        ts = event.fields.get("timestamp")
        if isinstance(ts, datetime):
            return (1, ts)
        return (0, datetime.min.replace(tzinfo=UTC))

    async def delete_related_event(self, event_id: str) -> None:
        """Port of ``DeleteRelatedEvent`` (elasticcasestore.go:776)."""
        err = validate_id(event_id, "relatedEventId")
        if err:
            raise RuntimeError(err)
        event = await self.get_related_event(event_id)
        if event is not None:
            await self._delete(event, "related", self._prepare_for_save(event))

    async def extract_common_observables(self, event: RelatedEvent) -> None | str:
        """Port of ``ExtractCommonObservables`` (elasticcasestore.go:1115).

        Returns the error string from the first failed ``create_artifact`` (the
        Go "return err" variant), or ``None``.
        """
        existing_values = await self._existing_artifact_values(event.case_id)
        for key, value in event.fields.items():
            value_str = "" if value is None else str(value)
            if not value_str or value_str in existing_values:
                continue
            if key in self._config.extract_common_observables:
                err = await self._create_observable(
                    event.case_id, value_str, key,
                )
                if err is not None:
                    return err
        return None

    async def _extract_observables(
        self, case_id: str, events: list[RelatedEvent],
    ) -> None:
        """Inline observable extraction for ``create_related_events``.

        Mirrors Go's loop in ``CreateRelatedEvents``: iterate the configured
        ``commonObservables`` keys per event and create an evidence artifact for
        each new value, swallowing per-artifact errors.
        """
        existing_values = await self._existing_artifact_values(case_id)
        for event in events:
            for obs in self._config.extract_common_observables:
                value = event.fields.get(obs)
                if value is None:
                    continue
                value_str = str(value)
                if not value_str or value_str in existing_values:
                    continue
                existing_values.add(value_str)
                await self._create_observable(event.case_id, value_str, obs)

    async def _existing_artifact_values(self, case_id: str) -> set[str]:
        """Collect the values of evidence artifacts already on the case.

        Go ignores the ``GetArtifacts`` error (``existingArtifacts, _ := ...``).
        """
        values: set[str] = set()
        try:
            existing = await self.get_artifacts(case_id, _EVIDENCE_GROUP, "")
        except RuntimeError:
            return values
        for artifact in existing:
            values.add(artifact.value)
        return values

    async def _create_observable(
        self, case_id: str, value: str, key: str,
    ) -> None | str:
        """Create one evidence artifact for an extracted observable value.

        Returns the error string on failure (logged as a warning), else ``None``.
        """
        artifact = Artifact()
        artifact.case_id = case_id
        artifact.value = value
        artifact.artifact_type = self._observables.get_type(value)
        artifact.group_type = _EVIDENCE_GROUP
        try:
            await self.create_artifact(artifact)
        except RuntimeError as exc:
            logger.warning(
                "automated observable extraction failed (key=%s caseId=%s "
                "artifactType=%s): %s",
                key, case_id, artifact.artifact_type, exc,
            )
            return str(exc)
        return None

    @staticmethod
    def _soc_id(event: RelatedEvent) -> str:
        value = event.fields.get("soc_id")
        return value if isinstance(value, str) else ""

    # ==================================================================
    # 15c — Artifacts + artifact streams (Go Create/Get/Update/Delete + ids)
    # ==================================================================

    def validate_artifact(self, artifact: Artifact) -> str | None:
        """Port of ``validateArtifact`` (elasticcasestore.go:216).

        Preserves Go's check order — notably ``value`` is validated before
        ``groupType`` — so the pinned error strings line up.
        """
        if artifact.id != "":
            err = validate_id(artifact.id, "artifactId")
            if err:
                return err
        if artifact.user_id != "":
            err = validate_id(artifact.user_id, "userId")
            if err:
                return err
        if artifact.case_id != "":
            err = validate_id(artifact.case_id, "caseId")
            if err:
                return err
        if artifact.stream_len != 0 and artifact.artifact_type != "file":
            return "Invalid streamLength"
        if artifact.kind:
            return "Field 'Kind' must not be specified"
        if artifact.operation:
            return "Field 'Operation' must not be specified"
        err = validate_string_required(
            artifact.value, 1, LONG_STRING_MAX, "value",
        )
        if err:
            return err
        err = validate_id(artifact.group_type, "groupType")
        if err:
            return err
        if artifact.group_id:
            err = validate_id(artifact.group_id, "groupId")
            if err:
                return err
        err = validate_string_required(
            artifact.artifact_type, 1, SHORT_STRING_MAX, "artifactType",
        )
        if err:
            return err
        err = validate_string(artifact.tlp, SHORT_STRING_MAX, "tlp")
        if err:
            return err
        err = validate_string(artifact.mime_type, SHORT_STRING_MAX, "mimeType")
        if err:
            return err
        err = validate_string(artifact.description, LONG_STRING_MAX, "description")
        if err:
            return err
        err = validate_string_array(
            artifact.tags, SHORT_STRING_MAX, MAX_ARRAY_ELEMENTS, "tags",
        )
        if err:
            return err
        err = validate_string(artifact.md5, SHORT_STRING_MAX, "md5")
        if err:
            return err
        err = validate_string(artifact.sha1, SHORT_STRING_MAX, "sha1")
        if err:
            return err
        return validate_string(artifact.sha256, SHORT_STRING_MAX, "sha256")

    def validate_artifact_stream(self, stream: ArtifactStream) -> str | None:
        """Port of ``validateArtifactStream`` (elasticcasestore.go:273)."""
        if stream.id != "":
            err = validate_id(stream.id, "artifactStreamId")
            if err:
                return err
        if stream.user_id != "":
            err = validate_id(stream.user_id, "userId")
            if err:
                return err
        if not stream.content:
            return "Missing stream content"
        if stream.kind:
            return "Field 'Kind' must not be specified"
        if stream.operation:
            return "Field 'Operation' must not be specified"
        return None

    async def create_artifact(self, artifact: Artifact) -> Artifact:
        """Port of ``CreateArtifact`` (elasticcasestore.go:888)."""
        err = self.validate_artifact(artifact)
        if err:
            raise RuntimeError(err)
        if artifact.id != "":
            raise RuntimeError("Unexpected ID found in new artifact")
        if artifact.case_id == "":
            raise RuntimeError("Missing Case ID in new artifact")
        if artifact.group_type == "":
            raise RuntimeError("Missing GroupType in new artifact")
        await self.get_case(artifact.case_id)  # confirm the case exists
        artifact.create_time = datetime.now(UTC)
        doc_id = await self._save(
            artifact, "artifact", self._prepare_for_save(artifact),
        )
        return await self.get_artifact(doc_id) or artifact

    async def get_artifact(self, artifact_id: str) -> Artifact | None:
        """Port of ``GetArtifact`` (elasticcasestore.go:916)."""
        err = validate_id(artifact_id, "artifactId")
        if err:
            raise RuntimeError(err)
        obj = await self._get(artifact_id, "artifact")
        return obj if isinstance(obj, Artifact) else None

    async def get_artifacts(
        self, case_id: str, group_type: str, group_id: str,
    ) -> list[Artifact]:
        """Port of ``GetArtifacts`` (elasticcasestore.go:931)."""
        err = validate_id(case_id, "caseId")
        if err:
            raise RuntimeError(err)
        # groupType is not technically an ID, but its values conform to one.
        err = validate_id(group_type, "groupType")
        if err:
            raise RuntimeError(err)
        if group_id:
            err = validate_id(group_id, "groupId")
            if err:
                raise RuntimeError(err)
        prefix = self._prefix
        group_id_term = ""
        if group_id:
            group_id_term = (
                f'AND {prefix}artifact.groupId:"{escape_lucene(group_id)}" '
            )
        query = (
            f'_index:"{self._index}" AND {prefix}kind:"artifact" AND '
            f'{prefix}artifact.caseId:"{escape_lucene(case_id)}" AND '
            f'{prefix}artifact.groupType:"{escape_lucene(group_type)}" '
            f"{group_id_term}| sortby {prefix}artifact.createTime^"
        )
        objects = await self._get_all(query, self._config.max_case_associations)
        return [o for o in objects if isinstance(o, Artifact)]

    async def update_artifact(self, artifact: Artifact) -> Artifact:
        """Port of ``UpdateArtifact`` (elasticcasestore.go:964).

        Preserves the immutable fields (create time, artifact/group type,
        value, stream metadata, hashes); only Description / Tlp / Tags / Ioc /
        Protected are mutable.
        """
        err = self.validate_artifact(artifact)
        if err:
            raise RuntimeError(err)
        if artifact.id == "":
            raise RuntimeError("Missing artifact ID")
        old = await self.get_artifact(artifact.id)
        if old is not None:
            artifact.create_time = old.create_time
            artifact.artifact_type = old.artifact_type
            artifact.value = old.value
            artifact.group_type = old.group_type
            artifact.group_id = old.group_id
            artifact.stream_len = old.stream_len
            artifact.mime_type = old.mime_type
            artifact.stream_id = old.stream_id
            artifact.md5 = old.md5
            artifact.sha1 = old.sha1
            artifact.sha256 = old.sha256
        doc_id = await self._save(
            artifact, "artifact", self._prepare_for_save(artifact),
        )
        return await self.get_artifact(doc_id) or artifact

    async def delete_artifact(self, artifact_id: str) -> None:
        """Port of ``DeleteArtifact`` (elasticcasestore.go:999).

        Cascades to the artifact's stream (logging but not raising on stream
        deletion failure). The Go analyzer-job cleanup (``Datastore.GetJobs`` /
        ``DeleteJob``) is a no-op here — that datastore dependency is not part of
        the Casestore port and is injected/handled at a higher layer.
        """
        artifact = await self.get_artifact(artifact_id)
        if artifact is None:
            return
        if artifact.stream_id:
            try:
                await self.delete_artifact_stream(artifact.stream_id)
            except RuntimeError as exc:
                logger.error(
                    "Unable to delete artifact stream; proceeding with artifact "
                    "deletion anyway (artifactStreamId=%s artifactId=%s): %s",
                    artifact.stream_id, artifact_id, exc,
                )
        await self._delete(artifact, "artifact", self._prepare_for_save(artifact))

    async def create_artifact_stream(self, stream: ArtifactStream) -> str:
        """Port of ``CreateArtifactStream`` (elasticcasestore.go:1038).

        Returns the new document id directly — there is no read-back.
        """
        err = self.validate_artifact_stream(stream)
        if err:
            raise RuntimeError(err)
        if stream.id != "":
            raise RuntimeError("Unexpected ID found in new artifactstream")
        stream.create_time = datetime.now(UTC)
        return await self._save(
            stream, "artifactstream", self._prepare_for_save(stream),
        )

    async def get_artifact_stream(self, stream_id: str) -> ArtifactStream | None:
        """Port of ``GetArtifactStream`` (elasticcasestore.go:1057)."""
        err = validate_id(stream_id, "artifactStreamId")
        if err:
            raise RuntimeError(err)
        obj = await self._get(stream_id, "artifactstream")
        return obj if isinstance(obj, ArtifactStream) else None

    async def delete_artifact_stream(self, stream_id: str) -> None:
        """Port of ``DeleteArtifactStream`` (elasticcasestore.go:1072)."""
        stream = await self.get_artifact_stream(stream_id)
        if stream is not None:
            await self._delete(
                stream, "artifactstream", self._prepare_for_save(stream),
            )

    async def get_case_ids_with_artifact(
        self, art_type: str, value: str,
    ) -> list[str]:
        """Port of ``GetCaseIdsWithArtifact`` (elasticcasestore.go:1081).

        Free-text ``art_type``/``value`` are escaped (Lucene injection defense)
        and the resulting case ids are returned unique in first-seen order.
        """
        err = validate_string_required(art_type, 1, LONG_STRING_MAX, "artType")
        if err:
            raise RuntimeError(err)
        err = validate_string_required(value, 1, LONG_STRING_MAX, "value")
        if err:
            raise RuntimeError(err)
        prefix = self._prefix
        query = (
            f'_index:"{self._index}" AND {prefix}kind:"artifact" AND '
            f'{prefix}artifact.artifactType:"{escape_lucene(art_type)}" AND '
            f'{prefix}artifact.value:"{escape_lucene(value)}"'
        )
        objects = await self._get_all(query, self._config.max_case_associations)
        case_ids: list[str] = []
        seen: set[str] = set()
        for obj in objects:
            if isinstance(obj, Artifact) and obj.case_id not in seen:
                seen.add(obj.case_id)
                case_ids.append(obj.case_id)
        return case_ids
