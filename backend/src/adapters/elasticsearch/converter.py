"""Elasticsearch response -> SOC domain mapping (pure layer).

Ports the ``convertFromElastic*`` family from
``server/modules/elastic/converter.go`` (response side):
flatten, parse_aggregation, parse_search_results, parse_scroll_results,
parse_msearch_results, parse_update_results, parse_index_results.

No ``async``, no network: pure transforms over already-decoded JSON dicts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.adapters.elasticsearch.field_caps import FieldDefinition, unmap_elastic_field
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
