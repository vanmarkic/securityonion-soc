"""Elasticsearch DSL query builder (pure layer).

Port of the request-building functions in
``server/modules/elastic/converter.go``: ``makeQuery``, ``formatSearch``,
``mapSearch``, ``stripSegmentOptions``. No I/O — these synchronous helpers
translate parsed SOC :class:`~src.domain.query.Query` objects into the
Elasticsearch query DSL ``dict`` shapes that the Go module emitted via
``json.WriteJson``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.adapters.elasticsearch.field_caps import FieldDefinition, map_elastic_field
from src.domain.query import SEGMENT_KIND_SEARCH, BaseSegment, Query


def format_search(value: str) -> str:
    """Trim spaces and default an empty search to ``*`` (Go ``formatSearch``)."""
    trimmed = value.strip(" ")  # Go strings.Trim(input, " ") — space only
    return trimmed if trimmed else "*"


def strip_segment_options(keys: list[str]) -> list[str]:
    """Drop ``-``-prefixed option keys (Go ``stripSegmentOptions``)."""
    return [k for k in keys if not k.startswith("-")]


def _rfc3339(dt: datetime) -> str:
    """Format like Go ``time.Format(time.RFC3339)`` (offset preserved, no micros)."""
    s = dt.strftime("%Y-%m-%dT%H:%M:%S")
    off = dt.utcoffset()
    if off is None or off.total_seconds() == 0:
        return s + "Z"
    total = int(off.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return f"{s}{sign}{total // 3600:02d}:{(total % 3600) // 60:02d}"


def map_search(defs: dict[str, FieldDefinition], search_segment: BaseSegment) -> BaseSegment:
    """Remap bare ``field:`` terms to their aggregatable ``.keyword`` twin.

    Mirrors Go ``mapSearch``: for each term whose raw value ends with ``:`` and
    is neither grouped nor quoted, the field name is remapped via
    ``map_elastic_field`` and the term rewritten in place.
    """
    delim = ":"
    for term in search_segment.terms:
        if term.raw.endswith(delim) and not term.grouped and not term.quoted:
            field = term.raw.strip(delim)  # Go strings.Trim(term.Raw, ":")
            new_field = map_elastic_field(defs, field)
            if new_field != field:
                term.raw = new_field + delim
    return search_segment


def make_query(
    defs: dict[str, FieldDefinition],
    parsed: Query,
    begin: datetime | None,
    end: datetime | None,
) -> dict[str, Any]:
    """Build the ``bool`` query DSL for a parsed query (Go ``makeQuery``).

    The four boolean clause arrays (``must``/``filter``/``should``/``must_not``)
    are always present, matching Go's ``make([]interface{}, 0)`` semantics. A
    ``@timestamp`` range clause is appended to ``must`` only when ``end`` is a
    non-zero time (Go ``!endTime.IsZero()``).
    """
    search_str = ""
    segment = parsed.named_segment(SEGMENT_KIND_SEARCH)
    if segment is not None:
        search_str = str(map_search(defs, segment))

    must: list[dict[str, Any]] = [
        {
            "query_string": {
                "query": format_search(search_str),
                "analyze_wildcard": True,
                "default_field": "*",
            }
        }
    ]

    if end is not None:  # Go: range clause only when EndTime is non-zero
        must.append(
            {
                "range": {
                    "@timestamp": {
                        "gte": _rfc3339(begin) if begin is not None else _rfc3339(end),
                        "lte": _rfc3339(end),
                        "format": "strict_date_optional_time",
                    }
                }
            }
        )

    return {
        "bool": {
            "must": must,
            "filter": [],
            "should": [],
            "must_not": [],
        }
    }
