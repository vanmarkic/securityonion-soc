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

Only the case CRUD + history methods are implemented in this task; the remaining
``Casestore`` protocol methods (comments, related events, artifacts, artifact
streams) follow in Task 15.
"""

from __future__ import annotations

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
from src.adapters.elasticsearch.store_base import save_with_audit
from src.domain.case import Case
from src.domain.event import EventSearchCriteria

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

    def _prepare_for_save(self, case: Case) -> str:
        """Port of ``prepareForSave`` (elasticcasestore.go:294).

        Stamps the requestor id, then strips the ``id``/``update_time`` from the
        document (ES already stores them) and returns the original id so the
        caller knows whether this is a create (``""``) or update.
        """
        case.user_id = self._requestor_id
        doc_id = case.id
        case.id = ""
        case.update_time = None
        return doc_id

    async def _save(self, case: Case, kind: str, doc_id: str) -> str:
        """Port of ``save`` (elasticcasestore.go:305) for case objects.

        Indexes the live document then the audit snapshot via the shared base,
        and returns the live document id.
        """
        document = convert_object_to_document_map(
            kind, case.model_dump(by_alias=True), self._prefix,
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
