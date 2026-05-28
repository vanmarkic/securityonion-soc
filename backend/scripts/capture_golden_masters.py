"""
Capture HTTP request/response pairs from the running Go server
as golden master fixtures for characterization testing.

Usage:
    python capture_golden_masters.py \
        --base-url https://localhost:9822 \
        --auth-token <bearer-token> \
        --output tests/characterization/golden_masters/

The script hits every known GET endpoint, records status codes and
response shapes, and writes JSON fixtures. These fixtures are later
replayed against the FastAPI server to verify behavioral equivalence.

Non-deterministic fields (timestamps, tokens, UUIDs) are tagged for
normalization during comparison.
"""
import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx

NON_DETERMINISTIC_FIELDS = frozenset({
    "srvToken", "createTime", "updateTime", "completeTime",
    "deleteTime", "timestamp", "onlineTime", "epochTime",
    "id", "userId", "sessionId",
})


@dataclass
class GoldenMaster:
    method: str
    path: str
    query_params: dict[str, str]
    status_code: int
    response_body: Any
    response_content_type: str
    response_headers: dict[str, str]
    non_deterministic_fields: list[str] = field(default_factory=list)
    captured_at: str = ""


ENDPOINTS: list[tuple[str, str, dict[str, str]]] = [
    # Info
    ("GET", "/api/info/", {}),

    # Config
    ("GET", "/api/config/", {}),
    ("GET", "/api/config/", {"advanced": "true"}),

    # Users
    ("GET", "/api/users/", {}),

    # Roles
    ("GET", "/api/roles", {}),
    ("GET", "/api/roles/permissions", {}),

    # Events
    ("GET", "/api/events/", {
        "query": "*",
        "range": "now-1h",
        "zone": "UTC",
        "format": "2006-01-02T15:04:05Z",
        "metricLimit": "10",
        "eventLimit": "5",
    }),

    # Detection (list via query - need at least one detection)
    # Individual detection GET requires an ID, skip for now

    # Cases (list)
    ("GET", "/api/case/", {}),

    # Jobs
    ("GET", "/api/jobs/", {"kind": ""}),

    # Grid
    ("GET", "/api/grid/", {}),
    ("GET", "/api/grid/status", {}),

    # Grid Members
    ("GET", "/api/gridmembers/", {}),

    # Nodes (via grid)
    ("GET", "/api/node", {}),

    # Query (active queries)
    ("GET", "/api/query/active", {"filter": "true"}),

    # Clients
    ("GET", "/api/clients/", {}),

    # Assistant sessions
    ("GET", "/api/assistant/sessions", {}),

    # Playbook (requires ID, skip parameterized)

    # Util - reverse lookup (PUT, needs body)
]

POST_ENDPOINTS: list[tuple[str, str, Any]] = [
    ("PUT", "/api/util/reverse-lookup", ["8.8.8.8", "1.1.1.1"]),
]


def find_non_deterministic(obj: Any, path: str = "") -> list[str]:
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            full = f"{path}.{k}" if path else k
            if k in NON_DETERMINISTIC_FIELDS:
                found.append(full)
            found.extend(find_non_deterministic(v, full))
    elif isinstance(obj, list):
        for i, item in enumerate(obj[:3]):
            found.extend(find_non_deterministic(item, f"{path}[{i}]"))
    return found


def capture_endpoint(
    client: httpx.Client,
    method: str,
    path: str,
    params: dict[str, str] | None = None,
    body: Any = None,
) -> GoldenMaster:
    if method == "GET":
        resp = client.get(path, params=params)
    elif method in ("PUT", "POST"):
        resp = client.request(method, path, json=body, params=params)
    else:
        raise ValueError(f"Unsupported method: {method}")

    content_type = resp.headers.get("content-type", "")
    try:
        response_body = resp.json()
    except Exception:
        response_body = resp.text if len(resp.content) < 10_000 else f"<binary {len(resp.content)} bytes>"

    nd_fields = find_non_deterministic(response_body)

    return GoldenMaster(
        method=method,
        path=path,
        query_params=params or {},
        status_code=resp.status_code,
        response_body=response_body,
        response_content_type=content_type,
        response_headers={
            k: v for k, v in resp.headers.items()
            if k.lower() in ("content-type", "x-request-id")
        },
        non_deterministic_fields=nd_fields,
        captured_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )


def safe_filename(method: str, path: str, params: dict[str, str]) -> str:
    slug = path.strip("/").replace("/", "_")
    name = f"{method.lower()}_{slug}"
    if params:
        suffix = "_".join(f"{k}={v}" for k, v in sorted(params.items()))
        name += f"__{suffix}"
    return name[:120] + ".json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture golden masters from Go server")
    parser.add_argument("--base-url", required=True, help="Go server URL (e.g., https://localhost:9822)")
    parser.add_argument("--auth-token", required=True, help="Bearer token for authentication")
    parser.add_argument("--output", default="tests/characterization/golden_masters/", help="Output directory")
    parser.add_argument("--verify-ssl", action="store_true", default=False, help="Verify SSL certificates")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    client = httpx.Client(
        base_url=args.base_url,
        headers={
            "Authorization": f"Bearer {args.auth_token}",
            "Accept": "application/json",
        },
        verify=args.verify_ssl,
        timeout=30.0,
    )

    total = len(ENDPOINTS) + len(POST_ENDPOINTS)
    success = 0
    errors = 0

    print(f"Capturing {total} endpoints from {args.base_url}")
    print(f"Output: {output_dir.resolve()}\n")

    for method, path, params in ENDPOINTS:
        try:
            gm = capture_endpoint(client, method, path, params=params)
            filename = safe_filename(method, path, params)
            (output_dir / filename).write_text(
                json.dumps(asdict(gm), indent=2, default=str)
            )
            status_icon = "OK" if gm.status_code < 400 else "WARN"
            nd_count = len(gm.non_deterministic_fields)
            print(f"  {status_icon}  {method} {path} -> {gm.status_code} ({nd_count} non-deterministic fields)")
            success += 1
        except Exception as e:
            print(f"  FAIL {method} {path} -> {e}", file=sys.stderr)
            errors += 1

    for method, path, body in POST_ENDPOINTS:
        try:
            gm = capture_endpoint(client, method, path, body=body)
            filename = safe_filename(method, path, {})
            (output_dir / filename).write_text(
                json.dumps(asdict(gm), indent=2, default=str)
            )
            nd_count = len(gm.non_deterministic_fields)
            print(f"  OK  {method} {path} -> {gm.status_code} ({nd_count} non-deterministic fields)")
            success += 1
        except Exception as e:
            print(f"  FAIL {method} {path} -> {e}", file=sys.stderr)
            errors += 1

    print(f"\nDone: {success} captured, {errors} failed")
    print(f"Golden masters saved to: {output_dir.resolve()}")

    manifest = {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base_url": args.base_url,
        "total_endpoints": total,
        "success": success,
        "errors": errors,
        "files": sorted(f.name for f in output_dir.glob("*.json") if f.name != "manifest.json"),
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
