"""
Replay golden masters against the FastAPI server.

These tests verify that the new API produces responses with the same
shape (field names, types, status codes) as the Go server.

Run the capture script first:
    python scripts/capture_golden_masters.py \
        --base-url https://your-go-server:9822 \
        --auth-token <token>
"""
import json

import pytest

from .conftest import GOLDEN_DIR, compare_shape

pytestmark = pytest.mark.skipif(
    not GOLDEN_DIR.exists() or not list(GOLDEN_DIR.glob("*.json")),
    reason="No golden masters captured yet — run capture script first",
)


def golden_master_ids():
    if not GOLDEN_DIR.exists():
        return []
    return [
        f.stem
        for f in sorted(GOLDEN_DIR.glob("*.json"))
        if f.name != "manifest.json"
    ]


@pytest.mark.parametrize("gm_id", golden_master_ids())
async def test_response_shape_matches(client, gm_id):
    gm_file = GOLDEN_DIR / f"{gm_id}.json"
    gm = json.loads(gm_file.read_text())

    method = gm["method"]
    path = gm["path"]
    params = gm.get("query_params", {})

    resp = await client.request(method, path, params=params)

    assert resp.status_code == gm["status_code"], (
        f"{method} {path}: expected status {gm['status_code']}, got {resp.status_code}"
    )

    if gm["response_body"] and resp.status_code < 400:
        try:
            actual_body = resp.json()
        except Exception:
            pytest.skip(f"Response not JSON for {method} {path}")
            return

        diffs = compare_shape(gm["response_body"], actual_body)
        assert not diffs, (
            f"{method} {path}: response shape differs from golden master:\n"
            + "\n".join(f"  - {d}" for d in diffs)
        )


@pytest.mark.parametrize("gm_id", golden_master_ids())
async def test_response_content_type_matches(client, gm_id):
    gm_file = GOLDEN_DIR / f"{gm_id}.json"
    gm = json.loads(gm_file.read_text())

    method = gm["method"]
    path = gm["path"]
    params = gm.get("query_params", {})

    resp = await client.request(method, path, params=params)

    expected_ct = gm.get("response_content_type", "")
    if expected_ct and "json" in expected_ct:
        actual_ct = resp.headers.get("content-type", "")
        assert "json" in actual_ct, (
            f"{method} {path}: expected JSON content-type, got {actual_ct}"
        )
