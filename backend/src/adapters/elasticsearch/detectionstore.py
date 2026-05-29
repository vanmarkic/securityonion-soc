"""ElasticDetectionstore — ES-backed implementation of the Detectionstore port.

Ports the detection-side of ``server/modules/elastic/elasticdetectionstore.go``
(``validateDetection``, ``prepareForSave``, ``save``/``get``/``getAll``,
``CreateDetection``/``GetDetection``/``GetDetectionByPublicId``/
``UpdateDetection``/``DeleteDetection``/``GetDetectionHistory``,
``DoesTemplateExist``) and the detection-comment side (``validateComment``,
``CreateComment``/``GetComment``/``GetComments``/``UpdateComment``/
``DeleteComment``).

Like the casestore, the store builds a ``{<prefix>detection: <det>, <prefix>kind:
"detection", '@timestamp': now}`` document, indexes it with ``refresh="true"``
(read-after-write), and writes an audit snapshot — all via the shared
``store_base`` (Task 13). Reads go through a composed :class:`ElasticEventstore`
(Go's ``store.server.Eventstore.Search``): a Lucene query string is run through
the same field-caps + ``make_query`` pipeline and each hit is mapped back to a
domain object via ``convert_elastic_event_to_object``.

Detection ids are deterministic: ``id = to_uuid(public_id)`` (Go ``util.ToUUID``),
so the same public id always maps to the same stable ES ``_id``.

Divergence from Go:

- The Python ``Detectionstore`` port (``src/ports/detections.py``) takes no
  ``ctx`` argument and performs no ``server.CheckAuthorized`` — authorization
  happens at the FastAPI route/dependency layer — so the Go ``CheckAuthorized``
  calls are dropped. The requestor id (Go ``web.ContextKeyRequestorId``) is
  supplied to the constructor and stamped onto each saved object's ``userId``.
- The Go ``GetAllDetections`` ``Query(max == -1)`` scroll path is **not** part
  of the Detectionstore port (it is a detection-engine concern), so it — and the
  scroll helper — are out of scope here. The history query uses the finite
  ``max_detection_associations`` limit, so no scroll is needed.

Task 16 implements detection CRUD + get-by-public-id + history + template
existence. Task 17 adds the detection-comment methods.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from elasticsearch import NotFoundError

from src.adapters.elasticsearch.client import ElasticClients
from src.adapters.elasticsearch.config import ElasticConfig
from src.adapters.elasticsearch.converter import (
    convert_elastic_event_to_object,
    convert_object_to_document_map,
)
from src.adapters.elasticsearch.escaping import (
    escape_lucene,
    to_uuid,
    validate_id,
    validate_public_id,
)
from src.adapters.elasticsearch.eventstore import ElasticEventstore
from src.adapters.elasticsearch.helpers import (
    AUDIT_DOC_ID,
    LONG_STRING_MAX,
    MAX_ARRAY_ELEMENTS,
    MAX_AUTHOR_LENGTH,
    SHORT_STRING_MAX,
    validate_string,
    validate_string_array,
    validate_string_required,
)
from src.adapters.elasticsearch.store_base import (
    delete_with_audit,
    save_with_audit,
)
from src.domain.case import Auditable
from src.domain.detection import Detection, DetectionComment
from src.domain.event import EventSearchCriteria

logger = logging.getLogger(__name__)

# Go model.EnginesByName / SupportedLanguages (model/detection.go:77,98). Each
# engine pins exactly one signature language; languages valid on their own form
# the supported set.
_ENGINE_LANGUAGE: dict[str, str] = {
    "suricata": "suricata",
    "strelka": "yara",
    "elastalert": "sigma",
}
_SUPPORTED_LANGUAGES: frozenset[str] = frozenset({"sigma", "suricata", "yara"})

# Go getAll uses this date layout for the now-anchored timeframe (Go
# "2006-01-02 3:04:05 PM").
_GETALL_DATE_FORMAT = "%Y-%m-%d %I:%M:%S %p"


class ElasticDetectionstore:
    """Detectionstore port backed by one or more ``AsyncElasticsearch`` clients."""

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
        return self._config.detection_index

    @property
    def _audit_index(self) -> str:
        return self._config.detection_audit_index

    @property
    def _prefix(self) -> str:
        return self._config.schema_prefix

    @property
    def _max_associations(self) -> int:
        return self._config.max_detection_associations

    # ------------------------------------------------------------------
    # validation (Go validateDetection)
    # ------------------------------------------------------------------

    def validate_detection(self, detection: Detection) -> str | None:
        """Port of ``validateDetection`` (elasticdetectionstore.go:120).

        Returns the first validation error string, or ``None`` when valid. The
        check order matches Go exactly so the pinned error strings line up.
        Engine and language are always validated (no empty bypass) and the
        engine must pin the supplied language.
        """
        if detection.id != "":
            err = validate_id(detection.id, "Id")
            if err:
                return err
        if detection.public_id != "":
            err = validate_public_id(detection.public_id, "publicId")
            if err:
                return err
        if detection.title != "":
            err = validate_string(detection.title, LONG_STRING_MAX, "title")
            if err:
                return err
        if detection.severity != "":
            err = validate_string(detection.severity, SHORT_STRING_MAX, "severity")
            if err:
                return err
        if detection.author != "":
            err = validate_string(detection.author, MAX_AUTHOR_LENGTH, "author")
            if err:
                return err
        if detection.description != "":
            err = validate_string(
                detection.description, LONG_STRING_MAX, "description",
            )
            if err:
                return err
        if detection.content != "":
            err = validate_string(detection.content, LONG_STRING_MAX, "content")
            if err:
                return err
        if detection.ruleset != "":
            err = validate_string_required(
                detection.ruleset, 0, SHORT_STRING_MAX, "ruleset",
            )
            if err:
                return err
        if detection.tags:
            err = validate_string_array(
                detection.tags, SHORT_STRING_MAX, MAX_ARRAY_ELEMENTS, "Tags",
            )
            if err:
                return err
        # Engine + language are always validated (no empty bypass).
        if detection.engine not in _ENGINE_LANGUAGE:
            return "invalid engine"
        if detection.language not in _SUPPORTED_LANGUAGES:
            return "invalid language"
        if _ENGINE_LANGUAGE[detection.engine] != detection.language:
            return "engine and language mismatch"
        if detection.kind:
            return "Field 'Kind' must not be specified"
        if detection.operation:
            return "Field 'Operation' must not be specified"
        return None

    # ------------------------------------------------------------------
    # save / get / get_all (Go save/get/getAll)
    # ------------------------------------------------------------------

    def _prepare_for_save(self, obj: Auditable, *, keep_id: bool = False) -> str:
        """Port of ``prepareForSave`` (elasticdetectionstore.go:513).

        Stamps the requestor id, then strips the ``update_time`` (and, unless an
        operation override is in play, the ``id``) from the document and returns
        the original id. The detection create path passes ``keep_id=True`` (Go's
        operation override) so the deterministic ``to_uuid`` id is preserved as
        the ES ``_id``.
        """
        obj.user_id = self._requestor_id
        doc_id = obj.id
        if not keep_id:
            obj.id = ""
        obj.update_time = None
        return doc_id

    async def _save(
        self,
        obj: Auditable,
        kind: str,
        doc_id: str,
        *,
        operation: str | None = None,
    ) -> str:
        """Port of ``save`` (elasticdetectionstore.go:188).

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
            operation=operation,
        )
        return result.document_id

    async def _delete(self, obj: Auditable, kind: str, doc_id: str) -> None:
        """Port of ``deleteDocument`` (elasticdetectionstore.go:251).

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
        """Port of ``get`` (elasticdetectionstore.go:300).

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
        """Port of ``getAll`` (elasticdetectionstore.go:315).

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
    # public Detectionstore API
    # ------------------------------------------------------------------

    async def create_detection(self, detection: Detection) -> Detection:
        """Port of ``CreateDetection`` (elasticdetectionstore.go:539).

        Validates, rejects a supplied id (Go's verbatim "...new comment" typo),
        rejects a duplicate (publicId + engine), stamps the create time, derives
        the deterministic ``to_uuid`` id, saves (live + audit, operation forced to
        ``create``), and reads the detection back to pick up the server-assigned
        update time.
        """
        err = self.validate_detection(detection)
        if err:
            raise RuntimeError(err)
        if detection.id != "":
            # Preserve Go's verbatim copy-paste error string.
            raise RuntimeError("Unexpected ID found in new comment")

        prefix = self._prefix
        dup_query = (
            f'_index:"{self._index}" AND {prefix}kind:"detection" AND '
            f'{prefix}detection.publicId:"{escape_lucene(detection.public_id)}" AND '
            f'{prefix}detection.engine:"{escape_lucene(detection.engine)}"'
        )
        duplicates = await self._get_all(dup_query, 1)
        if duplicates:
            raise RuntimeError("publicId already exists for this engine")

        detection.create_time = datetime.now(UTC)
        detection.id = to_uuid(detection.public_id)
        doc_id = await self._save(
            detection,
            "detection",
            self._prepare_for_save(detection, keep_id=True),
            operation="create",
        )
        return await self.get_detection(doc_id) or detection

    async def get_detection(self, detection_id: str) -> Detection:
        """Port of ``GetDetection`` (elasticdetectionstore.go:575)."""
        err = validate_id(detection_id, "detectId")
        if err:
            raise RuntimeError(err)
        obj = await self._get(detection_id, "detection")
        if not isinstance(obj, Detection):
            raise RuntimeError("Object not found")
        return obj

    async def get_detection_by_public_id(
        self, public_id: str,
    ) -> Detection | None:
        """Port of ``GetDetectionByPublicId`` (elasticdetectionstore.go:589)."""
        err = validate_public_id(public_id, "publicId")
        if err:
            raise RuntimeError(err)
        prefix = self._prefix
        query = (
            f'_index:"{self._index}" AND {prefix}kind:"detection" AND '
            f'{prefix}detection.publicId:"{escape_lucene(public_id)}"'
        )
        objects = await self._get_all(query, 1)
        for obj in objects:
            if isinstance(obj, Detection):
                return obj
        return None

    async def update_detection(self, detection: Detection) -> Detection:
        """Port of ``UpdateDetection`` (elasticdetectionstore.go:603).

        Validates, requires an id (``"Missing detection onion ID"``), saves, then
        reads back. The caller's ``id`` is restored after ``prepareForSave``
        clears it (Go's deferred restore).
        """
        err = self.validate_detection(detection)
        if err:
            raise RuntimeError(err)
        if detection.id == "":
            raise RuntimeError("Missing detection onion ID")
        original_id = detection.id
        try:
            doc_id = await self._save(
                detection, "detection", self._prepare_for_save(detection),
            )
            return await self.get_detection(doc_id)
        finally:
            detection.id = original_id

    async def delete_detection(self, detection_id: str) -> Detection:
        """Port of ``DeleteDetection`` (elasticdetectionstore.go:974).

        Reads the detection (raising if absent), deletes the live document, writes
        a ``delete`` audit snapshot, and returns the deleted detection.
        """
        detection = await self.get_detection(detection_id)
        await self._delete(detection, "detection", detection_id)
        return detection

    async def get_detection_history(self, detection_id: str) -> list[Any]:
        """Port of ``GetDetectionHistory`` (elasticdetectionstore.go:1023).

        Searches the audit index for every audit/comment doc carrying this
        detection id, ordered by ``@timestamp`` ascending. Free-text id is escaped
        (no ``validate_id``, matching Go).
        """
        escaped = escape_lucene(detection_id)
        prefix = self._prefix
        query = (
            f'_index:"{self._audit_index}" AND ('
            f'{prefix}{AUDIT_DOC_ID}:"{escaped}" OR '
            f'{prefix}detectioncomment.detectionId:"{escaped}") '
            f"| sortby @timestamp^"
        )
        return await self._get_all(query, self._max_associations)

    async def does_template_exist(self, template: str) -> bool:
        """Port of ``DoesTemplateExist`` (elasticdetectionstore.go:528).

        Returns ``True`` when the index template exists. The Python ES client
        raises ``NotFoundError`` for a 404 (Go inspects the status code instead),
        which is mapped to ``False``.
        """
        try:
            await self._clients.read_client.indices.get_index_template(
                name=template,
            )
        except NotFoundError:
            return False
        return True

    # ------------------------------------------------------------------
    # detection comments (Go validateComment / Create/Get/GetComments/
    # Update/DeleteComment) — Task 17
    # ------------------------------------------------------------------

    def validate_comment(self, comment: DetectionComment) -> str | None:
        """Port of ``validateComment`` (elasticdetectionstore.go:1098).

        Returns the first validation error string, or ``None`` when valid. The
        check order matches Go exactly so the pinned error strings line up:
        commentId -> detectionId -> userId -> kind -> operation -> value. Both
        ``id`` and ``detectionId`` use ``validate_id`` (5-50 chars, not the
        public-id validator), and ``value`` is always required (min 1).
        """
        if comment.id != "":
            err = validate_id(comment.id, "commentId")
            if err:
                return err
        if comment.detection_id != "":
            err = validate_id(comment.detection_id, "detectionId")
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
        return validate_string_required(comment.value, 1, LONG_STRING_MAX, "value")

    async def create_comment(self, comment: DetectionComment) -> DetectionComment:
        """Port of ``CreateComment`` (elasticdetectionstore.go:1123).

        Validates, rejects a supplied id (Go's verbatim "...new comment"),
        requires a detection id, confirms the parent detection exists, stamps the
        create time, saves (live + audit), and reads the comment back.
        """
        err = self.validate_comment(comment)
        if err:
            raise RuntimeError(err)
        if comment.id != "":
            raise RuntimeError("Unexpected ID found in new comment")
        if comment.detection_id == "":
            raise RuntimeError("Missing Detection ID in new comment")
        # Confirm the parent detection exists (raises "Object not found").
        await self.get_detection(comment.detection_id)
        comment.create_time = datetime.now(UTC)
        doc_id = await self._save(
            comment, "detectioncomment", self._prepare_for_save(comment),
        )
        return await self.get_comment(doc_id)

    async def get_comment(self, comment_id: str) -> DetectionComment:
        """Port of ``GetComment`` (elasticdetectionstore.go:1154)."""
        err = validate_id(comment_id, "commentId")
        if err:
            raise RuntimeError(err)
        obj = await self._get(comment_id, "detectioncomment")
        if not isinstance(obj, DetectionComment):
            raise RuntimeError("Object not found")
        return obj

    async def get_comments(self, detection_id: str) -> list[DetectionComment]:
        """Port of ``GetComments`` (elasticdetectionstore.go:1170).

        Searches the live index for every comment carrying this detection id,
        ordered by ``so_detectioncomment.createTime`` ascending. The detection id
        is validated with ``validate_id``.
        """
        err = validate_id(detection_id, "detectionId")
        if err:
            raise RuntimeError(err)
        prefix = self._prefix
        query = (
            f'_index:"{self._index}" AND {prefix}kind:"detectioncomment" AND '
            f'{prefix}detectioncomment.detectionId:"{escape_lucene(detection_id)}" '
            f"| sortby {prefix}detectioncomment.createTime^"
        )
        objects = await self._get_all(query, self._max_associations)
        return [o for o in objects if isinstance(o, DetectionComment)]

    async def update_comment(self, comment: DetectionComment) -> DetectionComment:
        """Port of ``UpdateComment`` (elasticdetectionstore.go:1191).

        Validates, requires an id (``"Missing comment ID"``), preserves the
        read-only create time from the stored comment, saves, then reads back.
        """
        err = self.validate_comment(comment)
        if err:
            raise RuntimeError(err)
        if comment.id == "":
            raise RuntimeError("Missing comment ID")
        old = await self.get_comment(comment.id)
        comment.create_time = old.create_time  # preserve read-only field
        doc_id = await self._save(
            comment, "detectioncomment", self._prepare_for_save(comment),
        )
        return await self.get_comment(doc_id)

    async def delete_comment(self, comment_id: str) -> None:
        """Port of ``DeleteComment`` (elasticdetectionstore.go:1218).

        Reads the comment (raising if absent), deletes the live document, and
        writes a ``delete`` audit snapshot.
        """
        comment = await self.get_comment(comment_id)
        await self._delete(comment, "detectioncomment", comment_id)
