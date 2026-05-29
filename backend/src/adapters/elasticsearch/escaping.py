from __future__ import annotations

import hashlib
import re

# Go uses RE2 `regexp.MatchString` with `^...$` (elasticdetectionstore.go:68/79,
# elasticassistantstore.go:147), where `$` anchors at end-of-text only. Python's `$`
# also matches just before a trailing "\n", so use `\Z` (end-of-string) to reject
# trailing-newline IDs and stay byte-faithful to Go. These validators gate `_id`
# values interpolated into Lucene queries, so the stricter anchor is security-relevant.
_ID_RE = re.compile(r"^[A-Za-z0-9\-_]{5,50}\Z")
_PUBLIC_ID_RE = re.compile(r"^[A-Za-z0-9\-_]{3,128}\Z")


def escape_lucene(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')  # backslash THEN quote


def escape_painless(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def to_uuid(s: str) -> str:
    # Faithful mirror of util/strings.go ToUUID (verified byte-identical):
    #   sha256 (32B) -> XOR-fold 32->16 (h[i] ^= h[16+i]) -> fold 16->15
    #   (h[0] ^= h[15]; h = h[:15]) -> 30 hex chars -> 8-4-(4..)-(b..)-12 layout
    #   with literal '4' version nibble and literal 'b' variant char.
    h = bytearray(hashlib.sha256(s.encode("utf-8")).digest())  # 32 bytes
    for i in range(16):
        h[i] ^= h[16 + i]
    h = h[:16]
    h[0] ^= h[15]
    h = h[:15]
    hx = h.hex()  # 30 hex chars
    # NOTE: indices are contiguous — do NOT skip chars: hx[12:15], hx[15:18], hx[18:]
    return f"{hx[0:8]}-{hx[8:12]}-4{hx[12:15]}-b{hx[15:18]}-{hx[18:]}"


def validate_id(id_: str, label: str) -> str | None:
    return None if _ID_RE.match(id_) else f"invalid ID for {label}"


def validate_public_id(id_: str, label: str) -> str | None:
    return None if _PUBLIC_ID_RE.match(id_) else f"invalid ID for {label}"
