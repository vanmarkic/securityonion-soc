"""Elasticsearch response -> SOC domain mapping (pure layer).

Ports the ``convertFromElastic*`` family from
``server/modules/elastic/converter.go`` (response side):
flatten, parse_aggregation, parse_search_results, parse_scroll_results,
parse_msearch_results, parse_update_results, parse_index_results.

No ``async``, no network: pure transforms over already-decoded JSON dicts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from src.adapters.elasticsearch.field_caps import FieldDefinition, unmap_elastic_field
from src.domain.case import (
    Artifact,
    ArtifactStream,
    Case,
    Comment,
    RelatedEvent,
)
from src.domain.detection import (
    Detection,
    DetectionComment,
    Override,
    OverrideParameters,
)
from src.domain.event import (
    EventMetric,
    EventMSearchResults,
    EventRecord,
    EventSearchResults,
    EventUpdateResults,
)

# Go: time.Time{}.Format("2006-01-02T15:04:05.000Z") for an unparseable timestamp.
_ZERO_TIMESTAMP = "0001-01-01T00:00:00.000Z"


class IndexResult:
    """Mirror of model.EventIndexResults (DocumentId + Success)."""

    def __init__(self, document_id: str = "", success: bool = False) -> None:
        self.document_id = document_id
        self.success = success


def flatten(
    defs: dict[str, FieldDefinition], data: dict[str, Any]
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    _flatten_kv(defs, out, "", data)
    return out


def _flatten_kv(
    defs: dict[str, FieldDefinition],
    out: dict[str, Any],
    prefix: str,
    value: dict[str, Any],
) -> None:
    for k, v in value.items():
        fk = prefix + k
        if isinstance(v, dict):
            _flatten_kv(defs, out, fk + ".", v)
        else:
            out[unmap_elastic_field(defs, fk)] = v


def _normalize_ts(payload: dict[str, Any]) -> tuple[datetime | None, str]:
    raw = payload.get("@timestamp")
    if raw is None:
        raw = payload.get("timestamp")
    dt: datetime | None = None
    if isinstance(raw, str):
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            dt = None
    if dt is None:
        return None, _ZERO_TIMESTAMP
    # ms-precision, literal-Z (Go ".000Z" layout on the parsed wall clock).
    ts = f"{dt.strftime('%Y-%m-%dT%H:%M:%S')}.{dt.microsecond // 1000:03d}Z"
    return dt, ts


def _parse_hit(defs: dict[str, FieldDefinition], hit: dict[str, Any]) -> EventRecord:
    rec = EventRecord()
    rec.source = hit.get("_index", "")
    rec.id = hit.get("_id", "")
    if hit.get("_type") is not None:
        rec.type = hit["_type"]
    if hit.get("_score") is not None:
        rec.score = hit["_score"]
    rec.payload = flatten(defs, hit.get("_source", {}))
    if hit.get("sort") is not None:
        rec.sort = hit["sort"]
    rec.time, rec.timestamp = _normalize_ts(rec.payload)
    return rec


def _total(hits: dict[str, Any]) -> int:
    total = hits.get("total", 0)
    if isinstance(total, dict):
        return int(total.get("value", 0))
    return int(total)


def parse_aggregation(
    name: str,
    agg_obj: dict[str, Any],
    keys: list[Any],
    metrics: dict[str, list[EventMetric]],
) -> None:
    buckets = agg_obj.get("buckets")
    if buckets is None:
        return
    lst = metrics.setdefault(name, [])
    for bucket in buckets:
        count = bucket.get("doc_count")
        if count is None:
            continue
        key = bucket.get("key_as_string")
        if key is None:
            key = bucket.get("key")
        if key is None:
            continue
        m = EventMetric()
        m.value = float(count)
        m.keys = [*keys, key]
        lst.append(m)
        for sub_name, sub in bucket.items():
            if isinstance(sub, dict) and sub_name.startswith("groupby_"):
                parse_aggregation(sub_name, sub, m.keys, metrics)


def _parse_common(
    defs: dict[str, FieldDefinition],
    body: dict[str, Any],
    res: EventSearchResults,
) -> str | None:
    """Shared search/scroll body parsing.

    Returns the invalid sentinel, the timeout error, the shard-failure error,
    or None. Events/metrics are populated before the shard-failure check so a
    partial result is preserved (matches Go).
    """
    if "took" not in body or "timed_out" not in body or "hits" not in body:
        return "Elasticsearch response is not a valid JSON search result"
    res.elapsed_ms = int(body["took"])
    if body["timed_out"]:
        return "Timeout while fetching results from Elasticsearch"
    hits = body["hits"]
    res.total_events = _total(hits)
    for hit in hits.get("hits", []):
        res.events.append(_parse_hit(defs, hit))
    shards = body.get("_shards", {})
    if shards.get("failed", 0) > 0:
        return "ERROR_QUERY_FAILED_ELASTICSEARCH"
    return None


def parse_search_results(
    defs: dict[str, FieldDefinition],
    body: dict[str, Any],
    res: EventSearchResults,
) -> str | None:
    err = _parse_common(defs, body, res)
    if err == "Elasticsearch response is not a valid JSON search result":
        return err
    # Aggregations parsed even on shard failure (events/metrics preserved).
    for name, agg in body.get("aggregations", {}).items():
        if isinstance(agg, dict):
            parse_aggregation(name, agg, [], res.metrics)
    return err  # timeout / shard-failure / None


def parse_scroll_results(
    defs: dict[str, FieldDefinition],
    body: dict[str, Any],
    res: EventSearchResults,
) -> str | None:
    return _parse_common(defs, body, res)


def parse_update_results(body: dict[str, Any], res: EventUpdateResults) -> str | None:
    if any(k not in body for k in ("took", "timed_out", "updated", "noops")):
        return "Elasticsearch response is not a valid JSON updated result"
    res.elapsed_ms = int(body["took"])
    if body["timed_out"]:
        return "Timeout while updating documents in Elasticsearch"
    res.updated_count = int(body["updated"])
    res.unchanged_count = int(body["noops"])
    return None


def parse_index_results(body: dict[str, Any]) -> IndexResult:
    return IndexResult(
        body.get("_id", ""),
        body.get("result") in ("created", "updated"),
    )


def parse_msearch_results(
    defs: dict[str, FieldDefinition],
    body: dict[str, Any],
    res: EventMSearchResults,
) -> str | None:
    res.elapsed_ms = int(body.get("took", 0))
    for response in body.get("responses", []):
        err_field = response.get("error")
        if err_field:
            if isinstance(err_field, dict):
                reason = err_field.get("reason")
                return reason if reason else str(err_field)
            return str(err_field)
        sub = EventSearchResults()
        e = parse_search_results(defs, response, sub)
        if e:
            return e
        res.responses.append(sub)
    return None


# ---------------------------------------------------------------------------
# Domain-object converters (TASK 9)
#
# Port of the ``convertElasticEventTo*`` family from converter.go. Each maps a
# flattened EventRecord payload (dotted ``<prefix><kind>.<field>`` keys) into a
# pydantic domain model. Field absence leaves the model default untouched (Go
# only assigns inside ``if value, ok := ...; ok``).
# ---------------------------------------------------------------------------


def convert_severity(sev: str) -> str:
    """Port of convertSeverity: numeric -> label, else lowercase passthrough."""
    s = sev.lower()
    if not s:
        return "high"
    return {"1": "low", "2": "medium", "3": "high", "4": "critical"}.get(s, s)


def _parse_object_time(payload: dict[str, Any], key: str) -> datetime | None:
    """Port of parseTime for object converters.

    Returns the stored datetime (already a datetime in the flattened payload),
    a datetime parsed from an RFC3339 string, or None when absent/unparseable.
    Go returns the zero time.Time for a missing/unparseable key; here we use
    None so the pydantic optional default is preserved.
    """
    value = payload.get(key)
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _fill_auditable(model: Any, rec: EventRecord, prefix: str) -> None:
    """Port of convertElasticEventToAuditable (id/update_time/kind/operation)."""
    model.id = rec.id
    model.update_time = rec.time
    payload = rec.payload
    kind = payload.get(prefix + "kind")
    if kind is not None:
        model.kind = kind
    operation = payload.get(prefix + "operation")
    if operation is not None:
        model.operation = operation


def convert_elastic_event_to_case(rec: EventRecord | None, prefix: str) -> Case | None:
    if rec is None:
        return None
    p = rec.payload
    c = Case()
    _fill_auditable(c, rec, prefix)
    base = prefix + "case."
    if base + "title" in p:
        c.title = p[base + "title"]  # type: ignore[assignment]
    if base + "description" in p:
        c.description = p[base + "description"]  # type: ignore[assignment]
    if base + "priority" in p:
        c.priority = int(cast(float, p[base + "priority"]))
    if base + "severity" in p:
        c.severity = convert_severity(p[base + "severity"])  # type: ignore[arg-type]
    if base + "status" in p:
        c.status = p[base + "status"]  # type: ignore[assignment]
    if base + "template" in p:
        c.template = p[base + "template"]  # type: ignore[assignment]
    if base + "userId" in p:
        c.user_id = p[base + "userId"]  # type: ignore[assignment]
    if base + "assigneeId" in p:
        c.assignee_id = p[base + "assigneeId"]  # type: ignore[assignment]
    if base + "tlp" in p:
        c.tlp = p[base + "tlp"]  # type: ignore[assignment]
    if base + "category" in p:
        c.category = p[base + "category"]  # type: ignore[assignment]
    if base + "pap" in p:
        c.pap = p[base + "pap"]  # type: ignore[assignment]
    tags = p.get(base + "tags")
    if tags is not None:
        c.tags = [str(t) for t in cast("list[Any]", tags)]
    c.create_time = _parse_object_time(p, base + "createTime")
    c.start_time = _parse_object_time(p, base + "startTime")
    c.complete_time = _parse_object_time(p, base + "completeTime")
    return c


def convert_elastic_event_to_comment(
    rec: EventRecord | None, prefix: str, *, feat_ttr: bool = False
) -> Comment | None:
    if rec is None:
        return None
    p = rec.payload
    obj = Comment()
    _fill_auditable(obj, rec, prefix)
    base = prefix + "comment."
    if base + "description" in p:
        obj.description = p[base + "description"]  # type: ignore[assignment]
    if base + "userId" in p:
        obj.user_id = p[base + "userId"]  # type: ignore[assignment]
    if base + "caseId" in p:
        obj.case_id = p[base + "caseId"]  # type: ignore[assignment]
    if feat_ttr and base + "hours" in p:
        obj.hours = float(cast(float, p[base + "hours"]))
    obj.create_time = _parse_object_time(p, base + "createTime")
    return obj


def convert_elastic_event_to_detection_comment(
    rec: EventRecord | None, prefix: str
) -> DetectionComment | None:
    if rec is None:
        return None
    p = rec.payload
    obj = DetectionComment()
    _fill_auditable(obj, rec, prefix)
    base = prefix + "detectioncomment."
    if base + "value" in p:
        obj.value = p[base + "value"]  # type: ignore[assignment]
    if base + "userId" in p:
        obj.user_id = p[base + "userId"]  # type: ignore[assignment]
    if base + "detectionId" in p:
        obj.detection_id = p[base + "detectionId"]  # type: ignore[assignment]
    obj.create_time = _parse_object_time(p, base + "createTime")
    return obj


def convert_elastic_event_to_related_event(
    rec: EventRecord | None, prefix: str
) -> RelatedEvent | None:
    if rec is None:
        return None
    p = rec.payload
    obj = RelatedEvent()
    _fill_auditable(obj, rec, prefix)
    fp = prefix + "related.fields."
    obj.fields = {k[len(fp):]: v for k, v in p.items() if k.startswith(fp)}
    if prefix + "related.userId" in p:
        obj.user_id = p[prefix + "related.userId"]  # type: ignore[assignment]
    if prefix + "related.caseId" in p:
        obj.case_id = p[prefix + "related.caseId"]  # type: ignore[assignment]
    obj.create_time = _parse_object_time(p, prefix + "related.createTime")
    return obj


def convert_elastic_event_to_artifact(
    rec: EventRecord | None, prefix: str
) -> Artifact | None:
    if rec is None:
        return None
    p = rec.payload
    obj = Artifact()
    _fill_auditable(obj, rec, prefix)
    base = prefix + "artifact."
    if base + "userId" in p:
        obj.user_id = p[base + "userId"]  # type: ignore[assignment]
    if base + "caseId" in p:
        obj.case_id = p[base + "caseId"]  # type: ignore[assignment]
    if base + "groupType" in p:
        obj.group_type = p[base + "groupType"]  # type: ignore[assignment]
    if base + "groupId" in p:
        obj.group_id = p[base + "groupId"]  # type: ignore[assignment]
    if base + "description" in p:
        obj.description = p[base + "description"]  # type: ignore[assignment]
    if base + "artifactType" in p:
        obj.artifact_type = p[base + "artifactType"]  # type: ignore[assignment]
    if base + "streamLength" in p:
        obj.stream_len = int(cast(float, p[base + "streamLength"]))
    if base + "streamId" in p:
        obj.stream_id = p[base + "streamId"]  # type: ignore[assignment]
    if base + "mimeType" in p:
        obj.mime_type = p[base + "mimeType"]  # type: ignore[assignment]
    if base + "value" in p:
        obj.value = p[base + "value"]  # type: ignore[assignment]
    if base + "tlp" in p:
        obj.tlp = p[base + "tlp"]  # type: ignore[assignment]
    tags = p.get(base + "tags")
    if tags is not None:
        obj.tags = [str(t) for t in cast("list[Any]", tags)]
    if base + "ioc" in p:
        obj.ioc = bool(p[base + "ioc"])
    if base + "md5" in p:
        obj.md5 = p[base + "md5"]  # type: ignore[assignment]
    if base + "sha1" in p:
        obj.sha1 = p[base + "sha1"]  # type: ignore[assignment]
    if base + "sha256" in p:
        obj.sha256 = p[base + "sha256"]  # type: ignore[assignment]
    if base + "protected" in p:
        obj.protected = bool(p[base + "protected"])
    obj.create_time = _parse_object_time(p, base + "createTime")
    return obj


def convert_elastic_event_to_artifact_stream(
    rec: EventRecord | None, prefix: str
) -> ArtifactStream | None:
    if rec is None:
        return None
    p = rec.payload
    obj = ArtifactStream()
    _fill_auditable(obj, rec, prefix)
    base = prefix + "artifactstream."
    if base + "userId" in p:
        obj.user_id = p[base + "userId"]  # type: ignore[assignment]
    if base + "content" in p:
        obj.content = p[base + "content"]  # type: ignore[assignment]
    obj.create_time = _parse_object_time(p, base + "createTime")
    return obj


def _override_param(override: dict[str, Any], key: str) -> str | None:
    value = override.get(key)
    return str(value) if value is not None else None


def convert_elastic_event_to_override(overrides: list[Any]) -> list[Override]:
    """Port of convertElasticEventToOverride.

    Each entry is a flat dict; track/ip/count/seconds/etc. nest under the
    pydantic ``override_parameters`` while type/isEnabled/note/timestamps stay
    on the Override itself.
    """
    out: list[Override] = []
    for entry in overrides:
        if not isinstance(entry, dict):
            continue
        ov = Override()
        params = OverrideParameters()
        if entry.get("type") is not None:
            ov.type = str(entry["type"])
        if "isEnabled" in entry:
            ov.is_enabled = bool(entry["isEnabled"])
        if entry.get("note") is not None:
            ov.note = str(entry["note"])
        ov.created_at = _parse_object_time(entry, "createdAt")
        ov.updated_at = _parse_object_time(entry, "updatedAt")
        if entry.get("thresholdType") is not None:
            params.threshold_type = str(entry["thresholdType"])
        if entry.get("regex") is not None:
            params.regex = str(entry["regex"])
        if entry.get("value") is not None:
            params.value = str(entry["value"])
        if entry.get("ip") is not None:
            params.ip = str(entry["ip"])
        if entry.get("track") is not None:
            params.track = str(entry["track"])
        if entry.get("count") is not None:
            params.count = int(entry["count"])
        if entry.get("seconds") is not None:
            params.seconds = int(entry["seconds"])
        if entry.get("customFilter") is not None:
            params.custom_filter = str(entry["customFilter"])
        ov.override_parameters = params
        out.append(ov)
    return out


def convert_elastic_event_to_detection(
    rec: EventRecord | None, prefix: str
) -> Detection | None:
    if rec is None:
        return None
    p = rec.payload
    obj = Detection()
    _fill_auditable(obj, rec, prefix)
    base = prefix + "detection."
    if base + "userId" in p:
        obj.user_id = p[base + "userId"]  # type: ignore[assignment]
    if base + "publicId" in p:
        obj.public_id = p[base + "publicId"]  # type: ignore[assignment]
    if base + "title" in p:
        obj.title = p[base + "title"]  # type: ignore[assignment]
    if base + "severity" in p:
        obj.severity = p[base + "severity"]  # type: ignore[assignment]
    if base + "author" in p:
        obj.author = p[base + "author"]  # type: ignore[assignment]
    if base + "description" in p:
        obj.description = p[base + "description"]  # type: ignore[assignment]
    if base + "content" in p:
        obj.content = p[base + "content"]  # type: ignore[assignment]
    if base + "isEnabled" in p:
        obj.is_enabled = bool(p[base + "isEnabled"])
    if base + "isReporting" in p:
        obj.is_reporting = bool(p[base + "isReporting"])
    if base + "isCommunity" in p:
        obj.is_community = bool(p[base + "isCommunity"])
    ruleset = p.get(base + "ruleset")
    if base + "ruleset" in p and ruleset is not None:
        obj.ruleset = str(ruleset)
    if base + "engine" in p:
        obj.engine = p[base + "engine"]  # type: ignore[assignment]
    if base + "language" in p:
        obj.language = p[base + "language"]  # type: ignore[assignment]
    if base + "license" in p:
        obj.license = p[base + "license"]  # type: ignore[assignment]
    tags = p.get(base + "tags")
    if tags is not None:
        obj.tags = [str(t) for t in cast("list[Any]", tags)]
    obj.source_created = _parse_object_time(p, base + "sourceCreated")
    obj.source_updated = _parse_object_time(p, base + "sourceUpdated")
    overrides = p.get(base + "overrides")
    if overrides is not None:
        obj.overrides = convert_elastic_event_to_override(cast("list[Any]", overrides))
    obj.create_time = _parse_object_time(p, base + "createTime")
    return obj


def convert_elastic_event_to_object(
    rec: EventRecord, prefix: str
) -> tuple[Any, str | None]:
    """Port of convertElasticEventToObject dispatch.

    Missing ``<prefix>kind`` -> (None, "Unknown object kind; id=<id>").
    Present but unrecognized kind -> (None, None) (matches Go's empty switch).
    """
    kind = rec.payload.get(prefix + "kind")
    if kind is None:
        return None, f"Unknown object kind; id={rec.id}"
    fn = _DISPATCH.get(str(kind))
    if fn is None:
        return None, None
    return fn(rec, prefix), None


_DISPATCH: dict[str, Any] = {
    "case": convert_elastic_event_to_case,
    "comment": convert_elastic_event_to_comment,
    "detectioncomment": convert_elastic_event_to_detection_comment,
    "related": convert_elastic_event_to_related_event,
    "artifact": convert_elastic_event_to_artifact,
    "artifactstream": convert_elastic_event_to_artifact_stream,
    "detection": convert_elastic_event_to_detection,
}
