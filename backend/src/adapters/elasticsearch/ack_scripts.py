"""Painless update-script builders for acknowledge / unacknowledge.

Ports ``addAcknowledgeScript`` / ``addUnacknowledgeScript`` from
``server/modules/elastic/elasticeventstore.go``. The painless source text is
copied **byte-for-byte** from the Go raw string literal (the Go source indents
with TABS; the literal begins with a newline and ends with a newline followed
by three tabs). It is asserted verbatim by
``elasticeventstore_test.go`` ``TestAddUpdateScript`` — do not reformat.

Divergence from Go: ``track_timing`` is gated by the ``FEAT_RPT`` licensing
feature in Go (``licensing.IsEnabled(licensing.FEAT_RPT)``). Licensing is not
yet ported, so the caller passes ``track_timing`` explicitly (defaults False).
"""

from __future__ import annotations

# Byte-for-byte copy of the Go raw string literal in addAcknowledgeScript.
_ACKNOWLEDGE_SCRIPT = (
    "\n"
    "\t\t\tboolean track_timing = params.trackTiming;\n"
    "\t\t\tboolean esc_bool = params.escBool;\n"
    "\t\t\tInstant now_instant = Instant.ofEpochMilli(params.nowMillis);\n"
    "\t\t\tZonedDateTime now_date = ZonedDateTime.ofInstant(now_instant, ZoneId.of('Z'));\n"
    "\t\t\tlong elapsed_seconds = 0;\n"
    "\t\t\tif (ctx._source.containsKey('@timestamp')) {\n"
    "\t\t\t\tZonedDateTime event_date = ZonedDateTime.parse(ctx._source['@timestamp']);\n"
    "\t\t\t\telapsed_seconds = ChronoUnit.SECONDS.between(event_date, now_date)\n"
    "\t\t\t}\n"
    "\n"
    "\t\t\tif (ctx._source.event.acknowledged != true) {\n"
    "\t\t\t\tctx._source.event.acknowledged = true;\n"
    "\t\t\t\tctx._source.event.acknowledged_by = params.userId;\n"
    "\t\t\t\tif (track_timing) {\n"
    "\t\t\t\t\tctx._source.event.acknowledged_timestamp = now_date;\n"
    "\t\t\t\t\tctx._source.event.acknowledged_elapsed_seconds = elapsed_seconds;\n"
    "\t\t\t\t}\n"
    "\t\t\t}\n"
    "\n"
    "\t\t\tif (ctx._source.event.escalated != true && esc_bool) {\n"
    "\t\t\t\tctx._source.event.escalated = esc_bool;\n"
    "\t\t\t\tctx._source.event.escalated_by = params.userId;\n"
    "\t\t\t\tif (track_timing) {\n"
    "\t\t\t\t\tctx._source.event.escalated_timestamp = now_date;\n"
    "\t\t\t\t\tctx._source.event.escalated_elapsed_seconds = elapsed_seconds;\n"
    "\t\t\t\t}\n"
    "\t\t\t}\n"
    "\t\t\t"
)

_UNACKNOWLEDGE_SCRIPT = "ctx._source.event.acknowledged = false;"


def build_acknowledge_script(
    *,
    now_millis: int,
    escalate: bool,
    user_id: str,
    track_timing: bool = False,
) -> tuple[list[str], dict[str, object]]:
    """Build the painless acknowledge script + params (Go addAcknowledgeScript)."""
    params: dict[str, object] = {
        "trackTiming": track_timing,
        "escBool": escalate,
        "nowMillis": now_millis,
        "userId": user_id,
    }
    return [_ACKNOWLEDGE_SCRIPT], params


def build_unacknowledge_script() -> tuple[list[str], dict[str, object]]:
    """Build the painless unacknowledge script (Go addUnacknowledgeScript)."""
    return [_UNACKNOWLEDGE_SCRIPT], {}
