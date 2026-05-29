"""Tests for the painless ack/unack script builders.

Verbatim painless text ported byte-for-byte from
``server/modules/elastic/elasticeventstore_test.go`` ``TestAddUpdateScript``
(the acknowledge-with-escalate script literal, lines 1025-1053).
"""

from src.adapters.elasticsearch.ack_scripts import (
    build_acknowledge_script,
    build_unacknowledge_script,
)

# Byte-for-byte copy of the Go raw string literal asserted in
# elasticeventstore_test.go (TestAddUpdateScript). The Go source indents with
# TABS, the literal starts with a leading newline, and ends with a newline
# followed by three tabs before the closing backtick. DO NOT reformat.
_GO_ACK_SCRIPT = (
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


def test_acknowledge_script_text_verbatim():
    scripts, params = build_acknowledge_script(
        now_millis=1700000000000,
        escalate=False,
        user_id="u1",
        track_timing=False,
    )
    assert scripts[0] == _GO_ACK_SCRIPT
    assert params["userId"] == "u1"
    assert params["nowMillis"] == 1700000000000
    assert params["escBool"] is False
    assert params["trackTiming"] is False


def test_acknowledge_script_sets_escalate_and_track_timing_params():
    scripts, params = build_acknowledge_script(
        now_millis=1700000000000,
        escalate=True,
        user_id="admin",
        track_timing=True,
    )
    # Single script regardless of escalate flag (escalate gated inside painless).
    assert len(scripts) == 1
    assert "esc_bool = params.escBool" in scripts[0]
    assert "ctx._source.event.escalated_by = params.userId;" in scripts[0]
    assert params["escBool"] is True
    assert params["trackTiming"] is True
    assert params["userId"] == "admin"


def test_unacknowledge_script_verbatim():
    scripts, params = build_unacknowledge_script()
    assert scripts == ["ctx._source.event.acknowledged = false;"]
    assert params == {}
