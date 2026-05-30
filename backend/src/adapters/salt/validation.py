"""Setting value validation — ported 1:1 from syntax/validator.go (+ yaml/json).

A setting's value is rejected outright if it contains a MATCHED pair of Jinja
delimiters (``{# #}`` / ``{{ }}`` / ``{% %}``) — those are not supported and
raise ``ERROR_JINJA_NOT_SUPPORTED``. Otherwise the value is validated according
to its declared syntax: ``yaml``/``yml`` parse as YAML, ``json``/``suricata``
parse as JSON, and any other (or empty) syntax is accepted as-is.

Errors are raised as :class:`ValueError` carrying the same message strings the Go
validator returns, so callers (and the porting tests) can assert on them exactly.
"""

from __future__ import annotations

import json

import yaml  # type: ignore[import-untyped]


def validate_yaml(value: str) -> None:
    """Validate ``value`` as YAML (mirror syntax/yaml.go ValidateYaml).

    An empty string is valid (yaml parses to ``None``). A parse failure raises a
    ``ValueError`` whose message is prefixed ``ERROR_MALFORMED_YAML -> `` followed
    by the underlying parser error, matching Go's cleaned-up message.
    """
    try:
        yaml.safe_load(value)
    except yaml.YAMLError as err:
        # Match Go's message: "ERROR_MALFORMED_YAML -> yaml: line 1: ..."
        raise ValueError(f"ERROR_MALFORMED_YAML -> {_yaml_error_message(err)}") from err


def validate_json(value: str) -> None:
    """Validate ``value`` as JSON (mirror syntax/json.go ValidateJson).

    Go's ValidateJson runs ``json.Unmarshal([]byte(value), &mapped)``; on an EMPTY
    string that errors ("unexpected end of JSON input"), so empty JSON is INVALID
    (unlike empty YAML, which parses to ``nil`` and is valid). Any parse failure —
    including the empty string — raises ``ERROR_MALFORMED_JSON``.
    """
    try:
        json.loads(value)
    except (ValueError, TypeError) as err:
        raise ValueError("ERROR_MALFORMED_JSON") from err


def validate(value: str, syntax: str) -> None:
    """Validate ``value`` for the given ``syntax`` (mirror syntax/validator.go Validate).

    Raises ``ValueError`` on failure; returns ``None`` when the value is valid (or
    when the syntax is not one we validate).
    """
    if (
        ("{#" in value and "#}" in value)
        or ("{{" in value and "}}" in value)
        or ("{%" in value and "%}" in value)
    ):
        raise ValueError("ERROR_JINJA_NOT_SUPPORTED")

    lowered = syntax.lower()
    if lowered in ("yaml", "yml"):
        validate_yaml(value)
    elif lowered in ("json", "suricata"):
        validate_json(value)


def _yaml_error_message(err: yaml.YAMLError) -> str:
    """Render a PyYAML error close to Go's gopkg.in/yaml.v3 message.

    Go emits e.g. ``yaml: line 1: did not find expected ',' or ']'``. PyYAML's
    ``str(err)`` carries more detail; we extract a ``yaml: line N: <problem>``
    shape when we can, otherwise fall back to a single-line rendering.
    """
    if isinstance(err, yaml.MarkedYAMLError) and err.problem is not None:
        line = err.problem_mark.line + 1 if err.problem_mark is not None else 0
        return f"yaml: line {line}: {err.problem}"
    return "yaml: " + " ".join(str(err).split())
