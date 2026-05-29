from __future__ import annotations

import json
from datetime import datetime

# Constants mirrored from the Go elastic module.
MAX_ERROR_LENGTH = 4096  # elasticeventstore.go:34
AUDIT_DOC_ID = "audit_doc_id"  # elasticcasestore.go:33
SHORT_STRING_MAX = 100  # elasticcasestore.go:34
MAX_AUTHOR_LENGTH = 250  # elasticcasestore.go:35
LONG_STRING_MAX = 1000000  # elasticcasestore.go:36
MAX_ARRAY_ELEMENTS = 50  # elasticcasestore.go:37


def disable_cross_cluster_index(index: str) -> str:
    # Go: strings.SplitN(index, ":", 2); use piece[1] only when a colon exists.
    return index.split(":", 1)[1] if ":" in index else index


def transform_index(index: str) -> str:
    # Go: strings.ReplaceAll(index, "{today}", time.Now().Format("2006.01.02"))
    return index.replace("{today}", datetime.now().strftime("%Y.%m.%d"))


def truncate(value: str, max_len: int) -> str:
    # Go: if len(input) > maxLogLength { return input[:maxLogLength] + "..." }
    return value[:max_len] + "..." if len(value) > max_len else value


def read_error_from_json(body: str) -> str:
    # Go: errorType + ": " + errorReason + " -> " + errorDetails, where
    # errorDetails is truncated to MAX_ERROR_LENGTH only when it exceeds it.
    etype, reason = "", ""
    try:
        err = json.loads(body).get("error", {})
        if isinstance(err, dict):
            etype = str(err.get("type", "") or "")
            reason = str(err.get("reason", "") or "")
    except (ValueError, AttributeError):
        etype, reason = "", ""
    details = body[:MAX_ERROR_LENGTH] if len(body) > MAX_ERROR_LENGTH else body
    return f"{etype}: {reason} -> {details}"


def validate_string_required(s: str, lo: int, hi: int, label: str) -> str | None:
    # Go uses len(str) on a Go string, i.e. byte length -> len(s.encode("utf-8")).
    n = len(s.encode("utf-8"))
    if n > hi:
        return f"{label} is too long ({n}/{hi})"
    if n < lo:
        return f"{label} is too short ({n}/{lo})"
    return None


def validate_string(s: str, hi: int, label: str) -> str | None:
    return validate_string_required(s, 0, hi, label)


def validate_string_array(arr: list[str], max_len: int, max_elems: int, label: str) -> str | None:
    if len(arr) > max_elems:
        return f"Field '{label}' contains excessive elements ({len(arr)}/{max_elems})"
    for i, el in enumerate(arr):
        # Go hard-codes the lowercase element label "tag[%d]" (elasticcasestore.go:107).
        err = validate_string(el, max_len, f"tag[{i}]")
        if err:
            return err
    return None
