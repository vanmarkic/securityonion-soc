"""Jinja escape/unescape seam — ported 1:1 from syntax/jinja.go.

SaltStack pillar values may contain Jinja2 markup (``{{ }}``, ``{# #}``,
``{% %}``) that must not be evaluated while a setting round-trips through SOC.
``escape_jinja`` rewrites each delimiter pair to a safe sentinel token and
``unescape_jinja`` reverses it. The token strings are kept byte-for-byte
identical to the Go implementation so escaped values stored by either codebase
remain interchangeable.
"""

from __future__ import annotations

# Ordered (delimiter, sentinel) pairs, matching syntax/jinja.go exactly.
_JINJA_TOKENS: tuple[tuple[str, str], ...] = (
    ("{{", "[SO_JINJA_SL_START]"),
    ("}}", "[SO_JINJA_SL_END]"),
    ("{#", "[SO_JINJA_CM_START]"),
    ("#}", "[SO_JINJA_CM_END]"),
    ("{%", "[SO_JINJA_ML_START]"),
    ("%}", "[SO_JINJA_ML_END]"),
)


def escape_jinja(value: str) -> str:
    """Replace Jinja delimiters with safe sentinel tokens (Go EscapeJinja)."""
    for delimiter, sentinel in _JINJA_TOKENS:
        value = value.replace(delimiter, sentinel)
    return value


def unescape_jinja(value: str) -> str:
    """Replace sentinel tokens with their Jinja delimiters (Go UnescapeJinja)."""
    for delimiter, sentinel in _JINJA_TOKENS:
        value = value.replace(sentinel, delimiter)
    return value
