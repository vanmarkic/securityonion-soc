"""Observable classifier — port of ``server/modules/elastic/observables.go``.

Classifies a free-text artifact value into one of the SOC observable types
(``ip``, ``domain``, ``fqdn``, ``url``, ``filename``, ``uriPath``, ``hash``,
default ``other``). The evaluation order is fixed and must match ``case.js`` and
Go's ``order`` slice exactly, since several patterns overlap (e.g. an IP would
also match the hash regex's hex-only alternatives only by coincidence, but a
domain vs. fqdn distinction is order-sensitive).

The IP check uses Python's :mod:`ipaddress` in place of Go's ``net.ParseIP``
(both accept dotted-quad IPv4 and full/compressed IPv6); every other type uses
the exact regex Go compiles. Go's ``regexp`` (RE2) anchors ``$`` at end-of-text,
so this port uses ``\\Z`` (end-of-string) rather than Python's ``$`` (which also
matches before a trailing newline) to stay byte-faithful — security-relevant
since classification feeds artifact creation.

Engine divergence (FQDN): Go's RE2 is a linear-time NFA and is immune to
catastrophic backtracking; Python's :mod:`re` is a backtracking engine. Go's
FQDN label group ``(([a-z0-9][a-z0-9\\-]*[a-z0-9]|[a-z0-9])+\\.)`` contains a
nested quantifier that, ported verbatim, backtracks exponentially on a long
unbroken alphanumeric run (e.g. a 64-char SHA-256 hash reaches the FQDN check
before HASH in the eval order and never returns — a DoS-class hang in
``create_related_events``). The label group is rewritten here to the
behaviorally-equivalent single-label form ``[a-z0-9](?:[a-z0-9\\-]*[a-z0-9])?``
(starts/ends alphanumeric, hyphens/alphanumerics in the middle). Equivalence to
Go's group was verified exhaustively over all ``{a,0,-}`` strings up to length 6
and by ~300k-input differential fuzzing; the rewrite is linear-time. The DOMAIN
regex has no nested quantifier and is left verbatim.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable

# Observable type constants (Go ObservableType string values).
IP = "ip"
FQDN = "fqdn"
DOMAIN = "domain"
URL = "url"
FILENAME = "filename"
URI_PATH = "uriPath"
HASH = "hash"
OTHER = "other"


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


# Regexes copied verbatim from observables.go (Go `$` -> Python `\Z`). Go uses
# `regexp.MatchString` (unanchored search), so only patterns that already pin
# `^`/`$` are anchored; the filename and uriPath patterns are intentionally
# partial matches, exactly as Go evaluates them.
_URL_RE = re.compile(r"^[a-zA-Z]+://")
# Go: ^(([a-z0-9][a-z0-9\-]*[a-z0-9]|[a-z0-9])+\.){2,}([a-z]{2,}|xn\-\-[a-z0-9]+)\.?$
# The nested-quantifier label group is rewritten to its linear single-label
# equivalent to avoid catastrophic backtracking (see module docstring).
_FQDN_RE = re.compile(
    r"^([a-z0-9](?:[a-z0-9\-]*[a-z0-9])?\.){2,}([a-z]{2,}|xn\-\-[a-z0-9]+)\.?\Z"
)
_DOMAIN_RE = re.compile(
    r"^([a-z0-9][a-z0-9\-]*[a-z0-9]|[a-z0-9])\.([a-z]{2,}|xn\-\-[a-z0-9]+)\.?\Z"
)
_FILENAME_RE = re.compile(r"(\/)?[\w,\\s-]+\.[A-Za-z]{3}\Z")
_URI_PATH_RE = re.compile(r"^\/[\w,\s-]")
_HASH_RE = re.compile(
    r"^[0-9a-fA-F]{32}\Z|^[0-9a-fA-F]{40}\Z|^[0-9a-fA-F]{64}\Z|^[0-9a-fA-F]{128}\Z"
)


class Observables:
    """Stateless classifier mirroring Go's ``Observables`` struct.

    The ``order`` list pins the evaluation order; each entry is either a regex
    (``re.Pattern.search``) or a predicate (the IP parser), checked in turn.
    """

    def __init__(self) -> None:
        # Note - this order must match case.js (Go observables.go:63).
        self._order: list[tuple[str, Callable[[str], bool]]] = [
            (IP, _is_ip),
            (DOMAIN, lambda s: _DOMAIN_RE.search(s) is not None),
            (FQDN, lambda s: _FQDN_RE.search(s) is not None),
            (URL, lambda s: _URL_RE.search(s) is not None),
            (FILENAME, lambda s: _FILENAME_RE.search(s) is not None),
            (URI_PATH, lambda s: _URI_PATH_RE.search(s) is not None),
            (HASH, lambda s: _HASH_RE.search(s) is not None),
        ]

    def get_type(self, expr: str) -> str:
        """Port of ``Observables.GetType`` (observables.go:69)."""
        for name, match in self._order:
            if match(expr):
                return name
        return OTHER
