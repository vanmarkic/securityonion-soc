import json
from pathlib import Path
from typing import Any

import pytest

GOLDEN_DIR = Path(__file__).parent / "golden_masters"

NON_DETERMINISTIC_FIELDS = frozenset({
    "srvToken", "createTime", "updateTime", "completeTime",
    "deleteTime", "timestamp", "onlineTime", "epochTime",
    "id", "userId", "sessionId",
})


@pytest.fixture
def golden_masters() -> dict[str, dict[str, Any]]:
    masters: dict[str, dict[str, Any]] = {}
    if not GOLDEN_DIR.exists():
        return masters
    for f in GOLDEN_DIR.glob("*.json"):
        if f.name == "manifest.json":
            continue
        masters[f.stem] = json.loads(f.read_text())
    return masters


def normalize(body: Any) -> Any:
    if isinstance(body, dict):
        return {
            k: "<non-deterministic>" if k in NON_DETERMINISTIC_FIELDS else normalize(v)
            for k, v in body.items()
        }
    if isinstance(body, list):
        return [normalize(item) for item in body]
    return body


def compare_shape(expected: Any, actual: Any, path: str = "") -> list[str]:
    diffs: list[str] = []

    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in expected:
            if key in NON_DETERMINISTIC_FIELDS:
                continue
            if key not in actual:
                diffs.append(f"{path}.{key}: missing in actual")
            else:
                diffs.extend(compare_shape(expected[key], actual[key], f"{path}.{key}"))
        for key in actual:
            if key not in expected and key not in NON_DETERMINISTIC_FIELDS:
                diffs.append(f"{path}.{key}: extra in actual (not in golden master)")
    elif isinstance(expected, list) and isinstance(actual, list):
        if len(expected) > 0 and len(actual) > 0:
            diffs.extend(compare_shape(expected[0], actual[0], f"{path}[0]"))
    elif type(expected) != type(actual):
        diffs.append(f"{path}: type mismatch (expected {type(expected).__name__}, got {type(actual).__name__})")

    return diffs
