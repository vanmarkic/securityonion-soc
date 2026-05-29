# Elasticsearch Adapter Implementation Plan

>**For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

## Goal

Port the Go `server/modules/elastic` module to a Python (FastAPI, async) Elasticsearch adapter that satisfies the four storage ports already defined in `backend/src/ports/`:

- `Eventstore` (`src/ports/events.py`): `search`, `acknowledge`, `get_active_queries`, `cancel_query`
- `Casestore` (`src/ports/cases.py`): case/comment/related-event/artifact/artifact-stream CRUD + history
- `Detectionstore` (`src/ports/detections.py`): detection + detection-comment CRUD + history
- `Assistantstore` (`src/ports/assistant.py`): sessions, chat history, usage

`DetectionEngine` and `AssistantManager` are behavioral/AI ports co-located in the same files and are **out of scope** for this adapter. The PCAP `joblookup` handler is an Eventstore/web concern and is **out of scope** here (port separately once Job/Datastore services land).

The authoritative reference is `/Users/dragan/Documents/securityonion-soc/docs/elasticsearch-adapter-research.md` and the Go sources under `server/modules/elastic/`. Where the research and the Go test files disagree, the Go `*_test.go` byte-level assertions win.

## Architecture

Hexagonal: the adapter is the ES-backed implementation of the storage ports. Strict pure/I-O split:

- **Pure layer** (`converter.py`, `query_builder.py`, `field_caps.py`, `escaping.py`, `helpers.py`): synchronous functions that translate SOC domain objects <-> ES DSL dicts and ES responses <-> domain objects. No `async`, no network. 100% unit-testable with no live ES.
- **I/O layer** (`eventstore.py`, `casestore.py`, `detectionstore.py`, `assistantstore.py`, `client.py`): thin `async` methods that build a request dict via the pure layer, call `AsyncElasticsearch`, then map the response via the pure layer. Unit-tested with a mocked async client (`unittest.mock.AsyncMock`); integration-tested against a real ES behind a skip marker.

**Context note:** unlike Go, the Python ports take **no `ctx` argument** and perform **no `CheckAuthorized`** inside the store — authorization happens at the FastAPI route/dependency layer (confirmed: `src/ports/events.py` `search(self, criteria)` etc. have no ctx). The adapter therefore **drops** all `server.CheckAuthorized` calls. The Go `es-security-runas-user` per-request header is also dropped for now (single service account); record it as a known divergence.

**Module layout** (all under `backend/src/adapters/elasticsearch/`):

```
src/adapters/elasticsearch/
  __init__.py
  config.py          # Pydantic ES config (snake_case keys + defaults)
  client.py          # build_async_client(), ElasticClients (primary + remotes)
  escaping.py        # escape_lucene, escape_painless, to_uuid, validate_id, validate_public_id
  helpers.py         # transform_index, disable_cross_cluster_index, truncate, read_error, flatten, validate_string*
  field_caps.py      # FieldDefinition, FieldCapsCache, map_elastic_field, unmap_elastic_field
  query_builder.py   # make_query, make_aggregation, make_timeline, calc_timeline_interval,
                     # format_search, map_search, strip_segment_options, build_search_request,
                     # build_scroll_request, build_msearch_request, build_update_request
  converter.py       # parse_search_results, parse_scroll_results, parse_update_results,
                     # parse_index_results, parse_aggregation, convert_*_to_object, convert_severity, ...
  eventstore.py      # ElasticEventstore (Eventstore port)
  casestore.py       # ElasticCasestore (Casestore port)
  detectionstore.py  # ElasticDetectionstore (Detectionstore port)
  assistantstore.py  # ElasticAssistantstore (Assistantstore port)
tests/adapters/elasticsearch/
  __init__.py
  fixtures/converter_response.json          # copied from Go module
  fixtures/converter_response_failure.json  # copied from Go module
  fixtures/fieldcaps_response.json          # copied from Go module
  test_*.py
tests/adapters/elasticsearch/integration/
  test_eventstore_integration.py            # @pytest.mark.skipif(no ES)
  ...
```

## Tech Stack

- `elasticsearch[async]` (official `AsyncElasticsearch`) — add to `backend/pyproject.toml`.
- Pydantic v2 for config + reuse of existing domain models (`src/domain/case.py`, `detection.py`, `assistant.py` are pydantic; `event.py`, `query.py` are plain classes).
- pytest + pytest-asyncio (`asyncio_mode = "auto"` already set), `unittest.mock.AsyncMock` for the client.
- Docker Compose (`docker-compose.dev.yml`) running a single-node ES for integration tests.

## Hard environment facts (apply to EVERY task)

- Backend root: `/Users/dragan/Documents/securityonion-soc/backend`. **Always** use `.venv/bin/python` (never bare `python`). Run all commands from the backend dir.
- Tests: `.venv/bin/python -m pytest <path> -v`
- Lint: `.venv/bin/python -m ruff check <path>`
- Types: `.venv/bin/python -m mypy <path>` (strict). Known pre-existing pydantic `call-arg` errors on `User(...)` are accepted — **do not** re-fix or touch them.
- Branch: `rewrite/v4`. One commit per task, conventional commit messages.
- Wiring via `create_app` in `src/main.py` using `application.dependency_overrides[...]` — **never** mutate the module-level `app`. Follow the established `_build_base_app`/`create_app` pattern.
- Each task < ~200 LOC. JSON byte-equality tests: serialize with `json.dumps(obj, sort_keys=True)` to match Go's key-sorted `json.WriteJson`.
- Time formatting: emit ms-precision UTC literal-Z, e.g. `f"{dt.strftime('%Y-%m-%dT%H:%M:%S')}.{dt.microsecond // 1000:03d}Z"`. RFC3339 for range bounds (offset preserved). `int(float(x))` (truncate toward zero) for `elapsed_ms`/`total_events`/`updated`/`noops`/priority/streamLen/count/seconds.

---

## TASK 1 — ES dependency + config + async client/transport

**Files**
- Modify: `backend/pyproject.toml` (add `elasticsearch[async]>=8.12,<9` to `dependencies`)
- Create: `backend/src/adapters/elasticsearch/__init__.py`
- Create: `backend/src/adapters/elasticsearch/config.py`
- Create: `backend/src/adapters/elasticsearch/client.py`
- Create: `backend/tests/adapters/elasticsearch/__init__.py`
- Create test: `backend/tests/adapters/elasticsearch/test_config.py`
- Create test: `backend/tests/adapters/elasticsearch/test_client.py`

**Step 1 — write failing tests**

`test_config.py`:
```python
from src.adapters.elasticsearch.config import ElasticConfig


def test_defaults_match_go_module():
    c = ElasticConfig()
    assert c.host_url == "elasticsearch"
    assert c.remote_host_urls == []
    assert c.verify_cert is True
    assert c.username == ""
    assert c.password == ""
    assert c.time_shift_ms == 120000
    assert c.default_duration_ms == 1800000
    assert c.es_search_offset_ms == 1800000
    assert c.timeout_ms == 300000
    assert c.cache_ms == 86400000
    assert c.index == "*:so-*"
    assert c.async_threshold == 10
    assert c.intervals == 25
    assert c.max_log_length == 1024
    assert c.cases_enabled is True
    assert c.detections_enabled is True
    assert c.assistant_enabled is True
    assert c.max_scroll_size == 10000
    # sub-store indices
    assert c.case_index == "*:so-case"
    assert c.audit_index == "*:so-casehistory"
    assert c.max_case_associations == 1000
    assert c.schema_prefix == "so_"
    assert c.detection_index == "*:so-detection"
    assert c.detection_audit_index == "*:so-detectionhistory"
    assert c.assistant_chat_index == "*:so-assistant-chat"
    assert c.assistant_session_index == "*:so-assistant-session"


def test_timeout_zero_coerced_to_default():
    c = ElasticConfig(timeout_ms=0)
    assert c.timeout_ms == 300000
```

`test_client.py`:
```python
from src.adapters.elasticsearch.client import ElasticClients, build_async_client


def test_build_client_no_auth_omits_basic_auth(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, hosts, **kwargs):
            captured["hosts"] = hosts
            captured.update(kwargs)

    monkeypatch.setattr("src.adapters.elasticsearch.client.AsyncElasticsearch", FakeClient)
    build_async_client("https://es:9200", "", "", verify_cert=True, timeout_ms=300000)
    assert captured["hosts"] == ["https://es:9200"]
    assert "basic_auth" not in captured
    assert captured["verify_certs"] is True  # verify_cert True -> verify_certs True
    assert captured["request_timeout"] == 300.0


def test_build_client_with_auth_and_verify_false(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, hosts, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("src.adapters.elasticsearch.client.AsyncElasticsearch", FakeClient)
    build_async_client("https://es:9200", "user", "pass", verify_cert=False, timeout_ms=120000)
    assert captured["basic_auth"] == ("user", "pass")
    assert captured["verify_certs"] is False  # InsecureSkipVerify = !verify_cert
    assert captured["request_timeout"] == 120.0


def test_clients_primary_and_remotes():
    clients = ElasticClients(primary="P", remotes=["R1", "R2"])
    assert clients.read_client == "P"          # reads/index/delete/fieldcaps/tasks use primary
    assert clients.all_clients == ["P", "R1", "R2"]  # update/ack fan out over all
```

**Step 2 — run to confirm red**
```
.venv/bin/python -m pytest tests/adapters/elasticsearch/test_config.py tests/adapters/elasticsearch/test_client.py -v
```
Expected: `ModuleNotFoundError: No module named 'src.adapters.elasticsearch.config'` (and/or `elasticsearch`).

**Step 3 — minimal implementation**

First add the dep and install:
```
.venv/bin/python -m pip install 'elasticsearch[async]>=8.12,<9'
```
Then edit `pyproject.toml` `[project].dependencies` to add `"elasticsearch[async]>=8.12,<9"`.

`config.py`:
```python
from pydantic import BaseModel, Field, field_validator


class ElasticConfig(BaseModel):
    host_url: str = "elasticsearch"
    remote_host_urls: list[str] = Field(default_factory=list)
    extract_common_observables: list[str] = Field(default_factory=list)
    verify_cert: bool = True
    username: str = ""
    password: str = ""
    time_shift_ms: int = 120000
    default_duration_ms: int = 1800000
    es_search_offset_ms: int = 1800000
    timeout_ms: int = 300000
    cache_ms: int = 86400000
    index: str = "*:so-*"
    async_threshold: int = 10
    intervals: int = 25
    max_log_length: int = 1024
    cases_enabled: bool = True
    lookup_tunnel_parent: bool = True
    detections_enabled: bool = True
    assistant_enabled: bool = True
    max_scroll_size: int = 10000
    # sub-store indices
    case_index: str = "*:so-case"
    audit_index: str = "*:so-casehistory"
    max_case_associations: int = 1000
    schema_prefix: str = "so_"
    detection_index: str = "*:so-detection"
    detection_audit_index: str = "*:so-detectionhistory"
    max_detection_associations: int = 1000
    assistant_chat_index: str = "*:so-assistant-chat"
    assistant_session_index: str = "*:so-assistant-session"
    bulk_indexer_worker_count: int = -1

    @field_validator("timeout_ms")
    @classmethod
    def _coerce_timeout(cls, v: int) -> int:
        return 300000 if v == 0 else v
```

`client.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field

from elasticsearch import AsyncElasticsearch


def build_async_client(
    host: str, user: str, password: str, *, verify_cert: bool, timeout_ms: int
) -> AsyncElasticsearch:
    kwargs: dict = {
        "verify_certs": verify_cert,  # Go: InsecureSkipVerify = !verify_cert
        "ssl_show_warn": False,
        "request_timeout": timeout_ms / 1000.0,
    }
    if user and password:
        kwargs["basic_auth"] = (user, password)
    return AsyncElasticsearch(hosts=[host], **kwargs)


@dataclass
class ElasticClients:
    primary: AsyncElasticsearch
    remotes: list[AsyncElasticsearch] = field(default_factory=list)

    @property
    def read_client(self) -> AsyncElasticsearch:
        return self.primary

    @property
    def all_clients(self) -> list[AsyncElasticsearch]:
        return [self.primary, *self.remotes]
```

**Step 4 — run green**
```
.venv/bin/python -m pytest tests/adapters/elasticsearch/test_config.py tests/adapters/elasticsearch/test_client.py -v
```

**Step 5 — ruff + mypy**
```
.venv/bin/python -m ruff check src/adapters/elasticsearch tests/adapters/elasticsearch
.venv/bin/python -m mypy src/adapters/elasticsearch
```

**Step 6 — commit**
```
feat(es): add elasticsearch[async] dep, ES config + async client/transport
```

---

## TASK 2 — Escaping + ID helpers (escape_lucene / escape_painless / to_uuid / validate_id)

These are pure, security-critical, byte-identical ports. Do them before the converter.

**Files**
- Create: `backend/src/adapters/elasticsearch/escaping.py`
- Create test: `backend/tests/adapters/elasticsearch/test_escaping.py`

**Step 1 — write failing test** (port from `util/strings_test.go` + recon regexes)
```python
import pytest
from src.adapters.elasticsearch.escaping import (
    escape_lucene, escape_painless, to_uuid, validate_id, validate_public_id,
)


def test_escape_lucene_order_backslash_then_quote():
    # backslash escaped FIRST, then double-quote
    assert escape_lucene(r'a\b"c') == r'a\\b\"c'


def test_escape_painless_backslash_then_singlequote():
    assert escape_painless(r"a\b'c") == r"a\\b\'c"


def test_to_uuid_deterministic_and_v4_shape():
    u = to_uuid("my-public-id")
    assert u == to_uuid("my-public-id")            # deterministic
    assert len(u) == 36
    assert u[14] == "4"                            # version nibble forced '4'
    assert u[19] == "b"                            # variant char forced 'b'


def test_to_uuid_matches_go_golden():
    # Golden value captured from Go util.ToUUID — REPLACE with the value
    # produced by running the Go TestToUUID (or `go test`) for this input.
    assert to_uuid("12345") == "<GO_GOLDEN_UUID>"


@pytest.mark.parametrize("ident", ["abc", "a-b_c", "x" * 128, "12345"])
def test_validate_public_id_ok(ident):
    assert validate_public_id(ident, "publicId") is None


@pytest.mark.parametrize("ident", ["", "ab", "x" * 129, "bad id", "a@b"])
def test_validate_public_id_rejects(ident):
    assert validate_public_id(ident, "publicId") == "invalid ID for publicId"


@pytest.mark.parametrize("ident", ["abcde", "a-b_c12", "x" * 50])
def test_validate_id_ok(ident):
    assert validate_id(ident, "caseId") is None


@pytest.mark.parametrize("ident", ["abcd", "x" * 51, "", "has space"])
def test_validate_id_rejects(ident):
    assert validate_id(ident, "caseId") == "invalid ID for caseId"
```

> Before running, capture `<GO_GOLDEN_UUID>` by running the Go test:
> `cd /Users/dragan/Documents/securityonion-soc && go test ./util/ -run TestToUUID -v` (or add a tiny `main` that prints `util.ToUUID("12345")`). Paste the exact value. `to_uuid` MUST be byte-identical because it drives stable detection `_id`s.

**Step 2 — run to confirm red**
```
.venv/bin/python -m pytest tests/adapters/elasticsearch/test_escaping.py -v
```
Expected: `ModuleNotFoundError`.

**Step 3 — minimal implementation** (port `util/strings.go`)
```python
from __future__ import annotations

import hashlib
import re

_ID_RE = re.compile(r"^[A-Za-z0-9\-_]{5,50}$")
_PUBLIC_ID_RE = re.compile(r"^[A-Za-z0-9\-_]{3,128}$")


def escape_lucene(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')  # backslash THEN quote


def escape_painless(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def to_uuid(s: str) -> str:
    # Port util.ToUUID: sha256 -> XOR-fold 32->16 -> fold 16->15 -> hex ->
    # format with forced '4' version nibble and 'b' variant char.
    digest = hashlib.sha256(s.encode("utf-8")).digest()  # 32 bytes
    folded = bytes(digest[i] ^ digest[i + 16] for i in range(16))  # 16 bytes
    # fold 16 -> 15 (mirror the exact Go fold; verify against golden value)
    b = bytearray(folded[:15])
    b[0] ^= folded[15]
    hexs = b.hex()  # 30 hex chars
    # 8-4-4-4-12 layout; force version '4' and variant 'b' (per Go)
    return f"{hexs[0:8]}-{hexs[8:12]}-4{hexs[13:16]}-b{hexs[17:20]}-{hexs[20:30]}"


def validate_id(id_: str, label: str) -> str | None:
    return None if _ID_RE.match(id_) else f"invalid ID for {label}"


def validate_public_id(id_: str, label: str) -> str | None:
    return None if _PUBLIC_ID_RE.match(id_) else f"invalid ID for {label}"
```

> The `to_uuid` fold/format sketch above is a starting point — **iterate** the slicing until `test_to_uuid_matches_go_golden` passes against the captured Go value. The hex-index layout (positions 13/17 etc.) encodes the forced nibbles; adjust to make the golden match exactly. This is the single most important byte-for-byte port.

**Step 4 — run green** (same command)

**Step 5 — ruff + mypy** (scope `src/adapters/elasticsearch/escaping.py` + test)

**Step 6 — commit**
```
feat(es): port escape_lucene/escape_painless/to_uuid + id validators (byte-identical)
```

---

## TASK 3 — Generic helpers (transform_index, disable_cross_cluster_index, truncate, read_error, validate_string*)

**Files**
- Create: `backend/src/adapters/elasticsearch/helpers.py`
- Create test: `backend/tests/adapters/elasticsearch/test_helpers.py`

**Step 1 — write failing test** (port `TestReadErrorFromJson`, disableCrossCluster cases, transformIndex)
```python
from datetime import datetime
from src.adapters.elasticsearch.helpers import (
    disable_cross_cluster_index, transform_index, truncate, read_error_from_json,
    validate_string, validate_string_required, validate_string_array,
)


def test_disable_cross_cluster_index():
    assert disable_cross_cluster_index("*:so-*") == "so-*"
    assert disable_cross_cluster_index("cluster:so-case") == "so-case"
    assert disable_cross_cluster_index("so-case") == "so-case"  # no colon -> unchanged


def test_transform_index_today():
    out = transform_index("logstash-{today}")
    today = datetime.now().strftime("%Y.%m.%d")
    assert out == f"logstash-{today}"


def test_truncate():
    assert truncate("abc", 10) == "abc"
    assert truncate("abcdef", 3) == "abc..."


def test_read_error_from_json_format():
    body = '{"error":{"type":"x_type","reason":"the reason"}}'
    msg = read_error_from_json(body)
    assert msg == 'x_type: the reason -> {"error":{"type":"x_type","reason":"the reason"}}'


def test_validate_string_lengths():
    assert validate_string("ok", 100, "title") is None
    assert validate_string("x" * 141, 100, "title") == "title is too long (141/100)"
    assert validate_string_required("", 1, 100, "title") == "title is too short (0/1)"


def test_validate_string_array_excess_elements():
    arr = ["a"] * 51
    assert validate_string_array(arr, 100, 50, "tags") == \
        "Field 'tags' contains excessive elements (51/50)"
    # element label is literally 'Tag[idx]'
    assert validate_string_array(["x" * 200], 100, 50, "tags") == "Tag[0] is too long (200/100)"
```

**Step 2 — run to confirm red** → `ModuleNotFoundError`.

**Step 3 — minimal implementation** (byte lengths via `len(s.encode("utf-8"))` to match Go `len()`)
```python
from __future__ import annotations

import json
from datetime import datetime

MAX_ERROR_LENGTH = 4096


def disable_cross_cluster_index(index: str) -> str:
    return index.split(":", 1)[1] if ":" in index else index


def transform_index(index: str) -> str:
    return index.replace("{today}", datetime.now().strftime("%Y.%m.%d"))


def truncate(value: str, max_len: int) -> str:
    return value[:max_len] + "..." if len(value) > max_len else value


def read_error_from_json(body: str) -> str:
    try:
        err = json.loads(body).get("error", {})
        etype, reason = err.get("type", ""), err.get("reason", "")
    except (ValueError, AttributeError):
        etype, reason = "", ""
    return f"{etype}: {reason} -> {body[:MAX_ERROR_LENGTH]}"


def validate_string_required(s: str, lo: int, hi: int, label: str) -> str | None:
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
        err = validate_string(el, max_len, f"Tag[{i}]")
        if err:
            return err
    return None
```

> Add module constants matching Go: `SHORT_STRING_MAX=100`, `MAX_AUTHOR_LENGTH=250`, `LONG_STRING_MAX=1000000`, `MAX_ARRAY_ELEMENTS=50`, `AUDIT_DOC_ID="audit_doc_id"`. (Some tests in later tasks assert exact length errors like `title is too long (140/100)`.)

**Step 4 — run green** · **Step 5 — ruff+mypy** · **Step 6 — commit**
```
feat(es): port index/error/string-validation helpers
```

---

## TASK 4 — Field-caps cache + map/unmap field

**Files**
- Create: `backend/src/adapters/elasticsearch/field_caps.py`
- Copy fixture: `backend/tests/adapters/elasticsearch/fixtures/fieldcaps_response.json` (from `server/modules/elastic/fieldcaps_response.json`)
- Create test: `backend/tests/adapters/elasticsearch/test_field_caps.py`

**Step 1 — write failing test** (port `TestMapElasticField`/`TestUnmapElasticField` + field-caps parse + multi-type preference)
```python
import json
from pathlib import Path

from src.adapters.elasticsearch.field_caps import (
    FieldDefinition, parse_field_caps, map_elastic_field, unmap_elastic_field,
)

FIX = Path(__file__).parent / "fixtures" / "fieldcaps_response.json"


def _defs() -> dict[str, FieldDefinition]:
    return {
        "smb.service": FieldDefinition("smb.service", "text", aggregatable=False, searchable=True),
        "smb.service.keyword": FieldDefinition("smb.service.keyword", "keyword", aggregatable=True, searchable=True),
        "agent.ip": FieldDefinition("agent.ip", "ip", aggregatable=True, searchable=True),
        "event.acknowledged": FieldDefinition("event.acknowledged", "boolean", aggregatable=True, searchable=True),
    }


def test_map_remaps_nonaggregatable_to_keyword():
    assert map_elastic_field(_defs(), "smb.service") == "smb.service.keyword"


def test_map_leaves_aggregatable_unchanged():
    assert map_elastic_field(_defs(), "agent.ip") == "agent.ip"
    assert map_elastic_field(_defs(), "event.acknowledged") == "event.acknowledged"


def test_unmap_strips_keyword_when_base_nonaggregatable():
    assert unmap_elastic_field(_defs(), "smb.service.keyword") == "smb.service"


def test_parse_field_caps_multitype_prefers_nonaggregatable():
    data = json.loads(FIX.read_text())
    defs = parse_field_caps(data)
    assert "smb.service" in defs
    # when a field has multiple type entries, NON-aggregatable wins
    multi = next((d for d in defs.values() if d.name and not d.aggregatable), None)
    assert multi is not None
```

**Step 2 — run to confirm red** → `ModuleNotFoundError`.

**Step 3 — minimal implementation**
```python
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass


@dataclass
class FieldDefinition:
    name: str
    field_type: str
    aggregatable: bool
    searchable: bool


def parse_field_caps(data: dict) -> dict[str, FieldDefinition]:
    out: dict[str, FieldDefinition] = {}
    for name, types in data.get("fields", {}).items():
        for _typ, meta in types.items():
            fd = FieldDefinition(name, meta.get("type", ""),
                                 bool(meta.get("aggregatable")), bool(meta.get("searchable")))
            existing = out.get(name)
            # prefer the NON-aggregatable definition; keep non-agg unless none set yet
            if existing is None or (existing.aggregatable and not fd.aggregatable):
                out[name] = fd
    return out


def map_elastic_field(defs: dict[str, FieldDefinition], field: str) -> str:
    fd = defs.get(field)
    if fd is not None and not fd.aggregatable:
        kw = defs.get(field + ".keyword")
        if kw is not None and kw.aggregatable:
            return field + ".keyword"
    return field


def unmap_elastic_field(defs: dict[str, FieldDefinition], field: str) -> str:
    if field.endswith(".keyword"):
        base = field[: -len(".keyword")]
        fd = defs.get(base)
        if fd is not None and not fd.aggregatable:
            return base
    return field


class FieldCapsCache:
    """Lazy/TTL field-caps cache (asyncio.Lock + cache_ms TTL)."""

    def __init__(self, cache_ms: int) -> None:
        self._cache_ms = cache_ms
        self._defs: dict[str, FieldDefinition] = {}
        self._cache_time = 0.0
        self._lock = asyncio.Lock()

    @property
    def defs(self) -> dict[str, FieldDefinition]:
        return self._defs

    async def refresh(self, fetch) -> None:  # fetch: async () -> dict (raw field_caps json)
        async with self._lock:
            now = time.monotonic() * 1000.0
            if self._cache_time != 0.0 and (now - self._cache_time) < self._cache_ms:
                return
            self._defs = parse_field_caps(await fetch())
            self._cache_time = now
```

**Step 4 — run green** · **Step 5 — ruff+mypy** · **Step 6 — commit**
```
feat(es): port field-caps cache + map/unmap_elastic_field
```

---

## TASK 5 — Converter part 1a: make_query (bool/query_string/time-range), format_search, map_search, strip_segment_options

**Files**
- Create: `backend/src/adapters/elasticsearch/query_builder.py`
- Create test: `backend/tests/adapters/elasticsearch/test_query_builder_make_query.py`

**Step 1 — write failing test** (port `TestFormatSearch`, `TestMapSearch`, and make_query shapes from `converter_test.go`)
```python
import json
from datetime import datetime, timezone

from src.adapters.elasticsearch.field_caps import FieldDefinition
from src.adapters.elasticsearch.query_builder import (
    format_search, strip_segment_options, make_query,
)
from src.domain.query import Query


def test_format_search():
    assert format_search("") == "*"
    assert format_search(" ") == "*"        # strip(' ') only
    assert format_search(r"\foo\bar") == r"\foo\bar"


def test_strip_segment_options():
    assert strip_segment_options(["one", "-flag", "two"]) == ["one", "two"]


def _q(s: str) -> Query:
    q = Query()
    assert q.parse(s) is None
    return q


def test_make_query_no_range_when_end_zero():
    body = make_query({}, _q("*"), None, None)
    assert body == {"bool": {
        "filter": [], "should": [], "must_not": [],
        "must": [{"query_string": {"query": "*", "analyze_wildcard": True, "default_field": "*"}}],
    }}


def test_make_query_with_range_serializes_like_go():
    begin = datetime(2020, 1, 2, 12, 13, 14, tzinfo=timezone.utc)
    end = datetime(2020, 1, 2, 13, 13, 14, tzinfo=timezone.utc)
    body = make_query({}, _q("abc AND def"), begin, end)
    must = body["bool"]["must"]
    assert must[0]["query_string"]["query"] == "abc AND def"
    assert must[1] == {"range": {"@timestamp": {
        "gte": "2020-01-02T12:13:14Z", "lte": "2020-01-02T13:13:14Z",
        "format": "strict_date_optional_time"}}}
    # empty arrays always present
    assert body["bool"]["filter"] == [] and body["bool"]["should"] == [] and body["bool"]["must_not"] == []


def test_map_search_remaps_bare_field_colon():
    defs = {
        "foo": FieldDefinition("foo", "text", aggregatable=False, searchable=True),
        "foo.keyword": FieldDefinition("foo.keyword", "keyword", aggregatable=True, searchable=True),
    }
    q = _q('foo: "bar"')
    body = make_query(defs, q, None, None)
    assert body["bool"]["must"][0]["query_string"]["query"] == 'foo.keyword: "bar"'
```

**Step 2 — run to confirm red** → `ImportError` / `AttributeError`.

**Step 3 — minimal implementation**
```python
from __future__ import annotations

from datetime import datetime

from src.adapters.elasticsearch.field_caps import FieldDefinition, map_elastic_field
from src.domain.query import SEGMENT_KIND_SEARCH, Query


def format_search(value: str) -> str:
    trimmed = value.strip(" ")  # Go strings.Trim(input, " ") — space only
    return trimmed if trimmed else "*"


def strip_segment_options(keys: list[str]) -> list[str]:
    return [k for k in keys if not k.startswith("-")]


def _rfc3339(dt: datetime) -> str:
    # offset preserved; 'Z' for UTC. Match Go time.RFC3339 (no microseconds).
    s = dt.strftime("%Y-%m-%dT%H:%M:%S")
    off = dt.utcoffset()
    if off is None or off.total_seconds() == 0:
        return s + "Z"
    total = int(off.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return f"{s}{sign}{total // 3600:02d}:{(total % 3600) // 60:02d}"


def map_search(defs: dict[str, FieldDefinition], search_segment) -> object:
    # For each term whose raw ends with ':' and is NOT grouped/quoted, remap field.
    for term in search_segment.terms:
        raw = term.raw
        if raw.endswith(":") and not getattr(term, "grouped", False) and not getattr(term, "quoted", False):
            field = raw[:-1]
            mapped = map_elastic_field(defs, field)
            if mapped != field:
                term.raw = mapped + ":"
    return search_segment


def make_query(defs: dict[str, FieldDefinition], parsed: Query,
               begin: datetime | None, end: datetime | None) -> dict:
    search_str = ""
    seg = parsed.named_segment(SEGMENT_KIND_SEARCH)
    if seg is not None:
        search_str = str(map_search(defs, seg))
    must: list[dict] = [{
        "query_string": {
            "query": format_search(search_str),
            "analyze_wildcard": True,
            "default_field": "*",
        }
    }]
    if end is not None:  # range only when EndTime non-zero
        must.append({"range": {"@timestamp": {
            "gte": _rfc3339(begin) if begin else _rfc3339(end),
            "lte": _rfc3339(end),
            "format": "strict_date_optional_time",
        }}})
    return {"bool": {"must": must, "filter": [], "should": [], "must_not": []}}
```

> The serialized dicts compare equal regardless of key order; the byte-equality is only asserted at the HTTP/`json.dumps(sort_keys=True)` boundary, which we test in Task 6. Verify `str(SearchSegment)` emits the space-after-colon (`foo: "bar"`) — `src/domain/query.py` already implements this.

**Step 4 — run green** · **Step 5 — ruff+mypy** · **Step 6 — commit**
```
feat(es): converter make_query + format_search/map_search/strip_segment_options
```

---

## TASK 6 — Converter part 1b: calc_timeline_interval + build_search_request/build_scroll_request/build_msearch_request/build_update_request (sort + byte-equality)

**Files**
- Modify: `backend/src/adapters/elasticsearch/query_builder.py`
- Create test: `backend/tests/adapters/elasticsearch/test_build_requests.py`

**Step 1 — write failing test** (port `TestCalcTimelineInterval`, `TestConvertToElasticRequestEmptyCriteria`, scroll empty, update, sort-by). Use `json.dumps(sort_keys=True)` for byte-equality against the Go strings captured in `converter_test.go`.
```python
import json
from datetime import datetime, timezone

from src.adapters.elasticsearch.query_builder import (
    calc_timeline_interval, build_search_request, build_scroll_request, build_update_request,
)
from src.domain.event import EventSearchCriteria, EventUpdateCriteria, SortCriteria
from src.domain.query import Query


def test_calc_timeline_interval_ladder():
    eight_h = (datetime(2020, 1, 1, 8, tzinfo=timezone.utc), datetime(2020, 1, 1, 16, tzinfo=timezone.utc))
    assert calc_timeline_interval(25, *eight_h) == "15m"
    one_s = (datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc), datetime(2020, 1, 1, 0, 0, 1, tzinfo=timezone.utc))
    assert calc_timeline_interval(25, *one_s) == "1s"
    huge = (datetime(1990, 1, 1, tzinfo=timezone.utc), datetime(2021, 1, 1, tzinfo=timezone.utc))
    assert calc_timeline_interval(25, *huge) == "30d"


def _sorted(d: dict) -> str:
    return json.dumps(d, sort_keys=True)


def test_build_search_empty_matches_go():
    c = EventSearchCriteria()
    c.metric_limit = 0
    c.event_limit = 25
    c.parsed_query = Query(); c.parsed_query.parse("*")
    expected = '{"query":{"bool":{"filter":[],"must":[{"query_string":{"analyze_wildcard":true,"default_field":"*","query":"*"}}],"must_not":[],"should":[]}},"size":25}'
    assert _sorted(build_search_request({}, 25, c)) == expected


def test_build_scroll_empty_matches_go():
    c = EventSearchCriteria()
    c.parsed_query = Query(); c.parsed_query.parse("*")
    expected = '{"query":{"bool":{"filter":[],"must":[{"query_string":{"analyze_wildcard":true,"default_field":"*","query":"*"}}],"must_not":[],"should":[]}},"size":10000}'
    # build_scroll_request(defs, scroll_criteria, max_scroll_size)
    assert _sorted(build_scroll_request({}, c, 10000)) == expected


def test_build_search_programmatic_sortfields_is_map():
    c = EventSearchCriteria()
    c.metric_limit = 0; c.event_limit = 25
    c.parsed_query = Query(); c.parsed_query.parse("*")
    c.sort_fields = [SortCriteria("name", "asc")]
    expected = '{"query":{"bool":{"filter":[],"must":[{"query_string":{"analyze_wildcard":true,"default_field":"*","query":"*"}}],"must_not":[],"should":[]}},"size":25,"sort":{"name":"asc"}}'
    assert _sorted(build_search_request({}, 25, c)) == expected


def test_build_update_request_two_scripts_with_range():
    c = EventUpdateCriteria()
    c.parsed_query = Query(); c.parsed_query.parse("event.dataset:alerts")
    c.begin_time = datetime(2020, 9, 24, 10, 11, 12, tzinfo=timezone.utc)
    c.end_time = datetime(2020, 9, 24, 12, 14, 15, tzinfo=timezone.utc)
    c.update_scripts = ["ctx._source.event.acknowledged=true",
                        "ctx._source.event.escalated=true"]
    body = build_update_request({}, c)
    assert body["script"]["source"] == \
        "ctx._source.event.acknowledged=true; ctx._source.event.escalated=true"
    assert body["script"]["lang"] == "painless"
    assert "range" in body["query"]["bool"]["must"][1]
```

> The empty `event_limit` defaults to 25 and `metric_limit` to 10 — tests set `metric_limit=0` to get the bare query (mirrors the Go tests). The `build_search_request` signature here is `(defs, event_limit_default, criteria)` but it reads `criteria.event_limit` for `size`; pass through. Sort-by **segment** (query language) is added in Task 7's group-by/sort sub-coverage — here cover only the programmatic `sort_fields` map form + empty + update.

**Step 2 — run to confirm red** → `ImportError`.

**Step 3 — minimal implementation** (append to `query_builder.py`)
```python
_INTERVAL_LADDER = [
    (3, "1s"), (7, "5s"), (13, "10s"), (23, "15s"), (45, "30s"), (180, "1m"),
    (420, "5m"), (780, "10m"), (1380, "15m"), (2700, "30m"), (5400, "1h"),
    (25200, "5h"), (54000, "10h"), (259200, "1d"), (604800, "5d"), (1296000, "10d"),
]


def calc_timeline_interval(intervals: int, begin: datetime, end: datetime) -> str:
    interval_seconds = (end - begin).total_seconds() / intervals
    for threshold, label in _INTERVAL_LADDER:
        if interval_seconds <= threshold:
            return label
    return "30d"


def _sort_from_criteria(parsed: Query, sort_fields) -> object | None:
    seg = parsed.named_segment("sortby")
    if seg is not None:
        arr = []
        for field in seg.raw_fields():
            order, name = "desc", field
            if field.endswith("^"):
                order, name = "asc", field[:-1]
            arr.append({name: {"order": order, "missing": "_last", "unmapped_type": "date"}})
        return arr
    if sort_fields:
        return {sc.field: sc.order for sc in sort_fields}
    return None


def build_search_request(defs, _default_limit: int, criteria) -> dict:
    body: dict = {"size": criteria.event_limit,
                  "query": make_query(defs, criteria.parsed_query,
                                      criteria.begin_time, criteria.end_time)}
    if criteria.search_after:
        body["search_after"] = criteria.search_after
    if criteria.metric_limit > 0:
        aggs = _build_aggregations(defs, criteria)  # implemented in Task 7
        if aggs:
            body["aggs"] = aggs
    sort = _sort_from_criteria(criteria.parsed_query, criteria.sort_fields)
    if sort is not None:
        body["sort"] = sort
    return body


def build_scroll_request(defs, criteria, max_scroll_size: int) -> dict:
    body: dict = {"size": max_scroll_size,
                  "query": make_query(defs, criteria.parsed_query,
                                      criteria.begin_time, criteria.end_time)}
    sort = _sort_from_criteria(criteria.parsed_query, criteria.sort_fields)
    if sort is not None:
        body["sort"] = sort
    return body


def build_msearch_request(defs, criteria) -> dict:
    # zero times -> no range
    return {"query": make_query(defs, criteria.parsed_query, None, None)}


def build_update_request(defs, criteria) -> dict:
    script: dict = {"source": "; ".join(criteria.update_scripts), "lang": "painless"}
    if criteria.params:
        script["params"] = criteria.params
    return {"query": make_query(defs, criteria.parsed_query,
                                criteria.begin_time, criteria.end_time),
            "script": script}
```

> Add a temporary `def _build_aggregations(defs, criteria): return {}` stub so Task 6 tests (metric_limit=0) pass; Task 7 replaces it with the real implementation.

**Step 4 — run green** · **Step 5 — ruff+mypy** · **Step 6 — commit**
```
feat(es): converter calc_timeline_interval + build search/scroll/msearch/update requests
```

---

## TASK 7 — Converter part 2a: aggregations (make_aggregation, make_timeline, _build_aggregations, sort-by segment)

**Files**
- Modify: `backend/src/adapters/elasticsearch/query_builder.py`
- Create test: `backend/tests/adapters/elasticsearch/test_aggregations.py`

**Step 1 — write failing test** (port `TestMakeAggregation`, `TestMakeTimeline`, `TestConvertToElasticRequestGroupBy/SortBy/GroupBySortByCriteria`)
```python
import json
from datetime import datetime, timezone

from src.adapters.elasticsearch.query_builder import (
    make_aggregation, make_timeline, build_search_request,
)
from src.domain.event import EventSearchCriteria
from src.domain.query import Query


def test_make_timeline():
    assert make_timeline("30m") == {"date_histogram": {
        "field": "@timestamp", "fixed_interval": "30m", "min_doc_count": 1}}


def test_make_aggregation_star_and_nesting():
    agg, name = make_aggregation({}, "groupby_0", ["one*", "two", "three*"], 10, ascending=False)
    assert name == "groupby_0|one"
    assert agg["terms"]["field"] == "one"
    assert agg["terms"]["missing"] == "__missing__"
    assert agg["terms"]["order"] == {"_count": "desc"}
    inner = agg["aggs"]["groupby_0|one|two"]
    assert "missing" not in inner["terms"]
    deepest = inner["aggs"]["groupby_0|one|two|three"]
    assert deepest["terms"]["missing"] == "__missing__"


def _sorted(d): return json.dumps(d, sort_keys=True)


def test_build_search_groupby_sortby_matches_go():
    c = EventSearchCriteria()
    c.metric_limit = 10; c.event_limit = 25
    c.begin_time = datetime(2020, 1, 2, 12, 13, 14, tzinfo=timezone.utc)
    c.end_time = datetime(2020, 1, 2, 13, 13, 14, tzinfo=timezone.utc)
    c.parsed_query = Query()
    c.parsed_query.parse(r'abc AND def AND q: "\\\\file\\path" | groupby ghi jkl* | groupby mno | sortby ghi jkl^')
    # Expected captured from converter_test.go TestConvertToElasticRequestGroupBySortByCriteria
    expected = '<PASTE_GO_EXPECTED_JSON_FROM_converter_test.go_line_137>'
    assert _sorted(build_search_request({}, 25, c)) == expected
```

> Capture the exact expected strings from `server/modules/elastic/converter_test.go` lines 106/125/137 (already located: `grep -n expectedJson server/modules/elastic/converter_test.go`). Paste each verbatim into the test (they include the heavily-escaped `query` text and the `bottom` agg). Cover at minimum: timeline-only (line 125), group-by (line 106), group-by+sort-by (line 137).

**Step 2 — run to confirm red** → assertion failure (stub returns `{}`).

**Step 3 — minimal implementation** (replace the `_build_aggregations` stub)
```python
def make_timeline(interval: str) -> dict:
    return {"date_histogram": {"field": "@timestamp", "fixed_interval": interval, "min_doc_count": 1}}


def make_aggregation(defs, prefix: str, keys: list[str], count: int,
                     *, ascending: bool) -> tuple[dict, str]:
    keys = list(keys)  # avoid mutating caller's list
    order = {"_count": "asc" if ascending else "desc"}
    agg_fields: dict = {}
    first = keys[0]
    if first.endswith("*"):
        first = first[:-1]
        keys[0] = first
        agg_fields["missing"] = "__missing__"
    agg_fields["field"] = map_elastic_field(defs, first)
    agg_fields["size"] = count
    agg_fields["order"] = order
    agg: dict = {"terms": agg_fields}
    name = f"{prefix}|{first}"
    if len(keys) > 1:
        inner, inner_name = make_aggregation(defs, name, keys[1:], count, ascending=ascending)
        agg["aggs"] = {inner_name: inner}
    return agg, name


def _build_aggregations(defs, criteria) -> dict:
    aggs: dict = {}
    if criteria.end_time is not None:
        from src.adapters.elasticsearch.config import ElasticConfig  # or pass intervals through
        interval = calc_timeline_interval(criteria.intervals if hasattr(criteria, "intervals") else 25,
                                          criteria.begin_time, criteria.end_time)
        aggs["timeline"] = make_timeline(interval)
    for idx, seg in enumerate(criteria.parsed_query.named_segments("groupby")):
        fields = strip_segment_options(seg.raw_fields())
        if not fields:
            continue
        prefix = f"groupby_{idx}"
        agg, name = make_aggregation(defs, prefix, fields, criteria.metric_limit, ascending=False)
        aggs[name] = agg
        if "bottom" not in aggs:
            bottom, _ = make_aggregation(defs, prefix, fields[:1], criteria.metric_limit, ascending=True)
            aggs["bottom"] = bottom
    return aggs
```

> `intervals` is config, not on the criteria — the cleanest fix is to thread `intervals` into `build_search_request(defs, intervals, criteria)` (rename the unused `_default_limit` param to `intervals`). Update Task 6's call sites and tests accordingly when implementing (Task 6 used `25`, which is the default — still correct). Note `make_aggregation` strips `*` **before** `bottom` is built from `fields[:1]`, so `bottom` field has no `*` — verified by the Go expected JSON.

**Step 4 — run green** · **Step 5 — ruff+mypy** · **Step 6 — commit**
```
feat(es): converter aggregations (terms/timeline/bottom) + sortby segment
```

---

## TASK 8 — Converter part 2b: response mapping (flatten, parse_aggregation, parse_search_results, parse_scroll_results, parse_msearch_results, parse_update_results, parse_index_results)

**Files**
- Modify (or create): `backend/src/adapters/elasticsearch/converter.py`
- Copy fixtures: `backend/tests/adapters/elasticsearch/fixtures/converter_response.json`, `converter_response_failure.json` (from Go module)
- Create test: `backend/tests/adapters/elasticsearch/test_parse_results.py`

**Step 1 — write failing test** (port `TestConvertFromElasticResults*`, `TestConvertFromElasticUpdateResults`, `TestConvertFromElasticIndexResults`, `TestConvertFromElasticMSearchResults`)
```python
import json
from pathlib import Path

from src.adapters.elasticsearch.converter import (
    flatten, parse_search_results, parse_update_results, parse_index_results,
)
from src.domain.event import EventSearchResults, EventUpdateResults

FIX = Path(__file__).parent / "fixtures"


def test_flatten_dotted_keys():
    assert flatten({}, {"a": {"b": 1}}) == {"a.b": 1}


def test_parse_search_results_success():
    body = json.loads((FIX / "converter_response.json").read_text())
    res = EventSearchResults()
    err = parse_search_results({}, body, res)
    assert err is None
    assert res.elapsed_ms == 9534
    assert res.total_events == 23689430        # hits.total may be a bare number
    assert len(res.events) == 25
    assert len(res.metrics) == 4               # 4 nested groupby metrics
    # timestamp normalization: ms-precision UTC literal Z
    assert res.events[0].timestamp.endswith("Z")


def test_parse_search_results_timed_out():
    res = EventSearchResults()
    err = parse_search_results({}, {"took": 123, "timed_out": True, "hits": {}}, res)
    assert err == "Timeout while fetching results from Elasticsearch"
    assert res.elapsed_ms == 123


def test_parse_search_results_invalid():
    res = EventSearchResults()
    err = parse_search_results({}, {}, res)
    assert err == "Elasticsearch response is not a valid JSON search result"


def test_parse_search_results_shard_failure_keeps_events():
    body = json.loads((FIX / "converter_response_failure.json").read_text())
    res = EventSearchResults()
    err = parse_search_results({}, body, res)
    assert err == "ERROR_QUERY_FAILED_ELASTICSEARCH"
    # events/metrics still populated


def test_parse_update_results():
    res = EventUpdateResults()
    err = parse_update_results({"took": 202, "timed_out": False, "updated": 3, "noops": 2}, res)
    assert err is None
    assert res.elapsed_ms == 202
    assert res.updated_count == 3
    assert res.unchanged_count == 2


def test_parse_index_results_success_states():
    r = parse_index_results({"_id": "abc", "result": "created"})
    assert r.document_id == "abc" and r.success is True
    assert parse_index_results({"_id": "x", "result": "deleted"}).success is False
```

**Step 2 — run to confirm red** → `ImportError`.

**Step 3 — minimal implementation** (port `converter.go` mappers; reuse hit-parsing helper for search+scroll)
```python
from __future__ import annotations

from datetime import datetime

from src.adapters.elasticsearch.field_caps import FieldDefinition, unmap_elastic_field
from src.domain.event import EventMetric, EventRecord


class IndexResult:
    def __init__(self, document_id: str = "", success: bool = False) -> None:
        self.document_id, self.success = document_id, success


def flatten(defs: dict[str, FieldDefinition], data: dict) -> dict:
    out: dict = {}
    _flatten_kv(defs, out, "", data)
    return out


def _flatten_kv(defs, out: dict, prefix: str, value: dict) -> None:
    for k, v in value.items():
        fk = prefix + k
        if isinstance(v, dict):
            _flatten_kv(defs, out, fk + ".", v)
        else:
            out[unmap_elastic_field(defs, fk)] = v


def _normalize_ts(payload: dict) -> tuple[datetime | None, str]:
    raw = payload.get("@timestamp") or payload.get("timestamp")
    if isinstance(raw, str):
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            dt = None
    else:
        dt = None
    if dt is None:
        return None, "0001-01-01T00:00:00.000Z"
    ts = f"{dt.strftime('%Y-%m-%dT%H:%M:%S')}.{dt.microsecond // 1000:03d}Z"
    return dt, ts


def _parse_hit(defs, hit: dict) -> EventRecord:
    rec = EventRecord()
    rec.source = hit.get("_index", "")
    rec.id = hit.get("_id", "")
    if "_type" in hit: rec.type = hit["_type"]
    if "_score" in hit and hit["_score"] is not None: rec.score = hit["_score"]
    rec.payload = flatten(defs, hit.get("_source", {}))
    rec.sort = hit.get("sort", [])
    rec.time, rec.timestamp = _normalize_ts(rec.payload)
    return rec


def _total(hits: dict) -> int:
    total = hits.get("total", 0)
    if isinstance(total, dict):
        return int(total.get("value", 0))
    return int(total)


def parse_aggregation(name: str, agg_obj: dict, keys: list, metrics: dict) -> None:
    buckets = agg_obj.get("buckets")
    if buckets is None:
        return
    lst = metrics.setdefault(name, [])
    for bucket in buckets:
        if "doc_count" not in bucket:
            continue
        key = bucket.get("key_as_string", bucket.get("key"))
        if key is None:
            continue
        m = EventMetric()
        m.value = float(bucket["doc_count"])
        m.keys = [*keys, key]
        lst.append(m)
        for sub_name, sub in bucket.items():
            if isinstance(sub, dict) and sub_name.startswith("groupby_"):
                parse_aggregation(sub_name, sub, m.keys, metrics)


def _parse_common(defs, body: dict, res, sentinel: str) -> str | None:
    if "took" not in body or "timed_out" not in body or "hits" not in body:
        return sentinel
    res.elapsed_ms = int(body["took"])
    if body["timed_out"]:
        return "Timeout while fetching results from Elasticsearch"
    hits = body["hits"]
    res.total_events = _total(hits)
    for hit in hits.get("hits", []):
        res.events.append(_parse_hit(defs, hit))
    shards = body.get("_shards", {})
    if shards.get("failed", 0) > 0:
        return "ERROR_QUERY_FAILED_ELASTICSEARCH"
    return None


def parse_search_results(defs, body: dict, res) -> str | None:
    err = _parse_common(defs, body, res,
                        "Elasticsearch response is not a valid JSON search result")
    if err == "Elasticsearch response is not a valid JSON search result":
        return err
    for name, agg in body.get("aggregations", {}).items():
        parse_aggregation(name, agg, [], res.metrics)
    return err  # may be timeout / shard-failure / None


def parse_scroll_results(defs, body: dict, res) -> str | None:
    return _parse_common(defs, body, res,
                        "Elasticsearch response is not a valid JSON search result")


def parse_update_results(body: dict, res) -> str | None:
    if any(k not in body for k in ("took", "timed_out", "updated", "noops")):
        return "Elasticsearch response is not a valid JSON updated result"
    res.elapsed_ms = int(body["took"])
    if body["timed_out"]:
        return "Timeout while updating documents in Elasticsearch"
    res.updated_count = int(body["updated"])
    res.unchanged_count = int(body["noops"])
    return None


def parse_index_results(body: dict) -> IndexResult:
    return IndexResult(body.get("_id", ""), body.get("result") in ("created", "updated"))


def parse_msearch_results(defs, body: dict, res) -> str | None:
    res.elapsed_ms = int(body.get("took", 0))
    for response in body.get("responses", []):
        if response.get("error"):
            err = response["error"]
            return err.get("reason", str(err)) if isinstance(err, dict) else str(err)
        from src.domain.event import EventSearchResults
        sub = EventSearchResults()
        e = parse_search_results(defs, response, sub)
        if e:
            return e
        res.responses.append(sub)
    return None
```

> If `parse_search_results` ordering of shard-failure vs timeout vs invalid matters, mirror Go: invalid → return immediately; timed_out → error but continue setting elapsed; shard-failure → error AFTER events/metrics parsed. The helper above returns the invalid sentinel only when validation fails. Confirm `EventRecord`/`EventMetric`/`EventSearchResults.responses` exist on the domain (event.py); add `responses: list` to `EventMSearchResults` domain if missing (separate trivial edit, note it).

**Step 4 — run green** · **Step 5 — ruff+mypy** · **Step 6 — commit**
```
feat(es): converter response mapping (flatten, parse search/scroll/msearch/update/index)
```

---

## TASK 9 — Converter part 2c: domain-object converters (convert_severity + convert_elastic_event_to_object dispatch for case/comment/related/artifact/artifactstream/detection/detectioncomment)

**Files**
- Modify: `backend/src/adapters/elasticsearch/converter.py`
- Create test: `backend/tests/adapters/elasticsearch/test_object_converters.py`

**Step 1 — write failing test** (port `TestConvertSeverity`, `TestConvertElasticEventToCase`, `...Artifact`, `...RelatedEvent`, `...Detection`, `...Object`)
```python
from src.adapters.elasticsearch.converter import (
    convert_severity, convert_elastic_event_to_object,
    convert_elastic_event_to_case, convert_elastic_event_to_related_event,
)
from src.domain.event import EventRecord


def test_convert_severity():
    assert convert_severity("") == "high"
    assert convert_severity("1") == "low"
    assert convert_severity("2") == "medium"
    assert convert_severity("3") == "high"
    assert convert_severity("4") == "critical"
    assert convert_severity("Critical") == "critical"
    assert convert_severity("unknown") == "unknown"


def _rec(payload: dict, id_: str = "abc12") -> EventRecord:
    r = EventRecord(); r.id = id_; r.payload = payload; return r


def test_convert_case_with_fields():
    rec = _rec({
        "so_kind": "case", "so_case.title": "T", "so_case.priority": 3.0,
        "so_case.severity": "2", "so_case.tags": ["a", "b"],
    })
    c = convert_elastic_event_to_case(rec, "so_")
    assert c.title == "T" and c.priority == 3 and c.severity == "medium" and c.tags == ["a", "b"]


def test_convert_related_event_dynamic_fields():
    rec = _rec({"so_kind": "related", "so_related.fields.foo": "bar", "so_related.caseId": "case1"})
    re_ = convert_elastic_event_to_related_event(rec, "so_")
    assert re_.fields["foo"] == "bar" and re_.case_id == "case1"


def test_dispatch_unknown_kind_missing_errors():
    obj, err = convert_elastic_event_to_object(_rec({}, "id77"), "so_")
    assert obj is None and err == "Unknown object kind; id=id77"


def test_dispatch_present_but_unrecognized_returns_none_none():
    obj, err = convert_elastic_event_to_object(_rec({"so_kind": "weird"}), "so_")
    assert obj is None and err is None
```

**Step 2 — run to confirm red** → `ImportError`.

**Step 3 — minimal implementation** (port the `convertElasticEventTo*` family + `convert_severity`; build pydantic domain models with snake_case fields)
```python
from src.domain.case import Artifact, ArtifactStream, Case, Comment, RelatedEvent
from src.domain.detection import Detection, DetectionComment


def convert_severity(sev: str) -> str:
    s = sev.lower()
    if not s:
        return "high"
    return {"1": "low", "2": "medium", "3": "high", "4": "critical"}.get(s, s)


def _fill_auditable(model, rec, prefix: str) -> None:
    model.id = rec.id
    model.update_time = rec.time
    payload = rec.payload
    if (prefix + "kind") in payload:
        model.kind = payload[prefix + "kind"]
    if (prefix + "operation") in payload:
        model.operation = payload[prefix + "operation"]


def convert_elastic_event_to_case(rec, prefix: str) -> Case:
    p, c = rec.payload, Case()
    _fill_auditable(c, rec, prefix)
    base = prefix + "case."
    c.title = p.get(base + "title", "")
    c.description = p.get(base + "description", "")
    if base + "priority" in p: c.priority = int(p[base + "priority"])
    c.severity = convert_severity(p.get(base + "severity", ""))
    c.status = p.get(base + "status", "")
    # ... template/userId/assigneeId/tlp/category/pap; tags nil-safe; create/start/complete times
    tags = p.get(base + "tags")
    if tags is not None:
        c.tags = list(tags)
    return c


def convert_elastic_event_to_related_event(rec, prefix: str) -> RelatedEvent:
    p, re_ = rec.payload, RelatedEvent()
    _fill_auditable(re_, rec, prefix)
    fp = prefix + "related.fields."
    re_.fields = {k[len(fp):]: v for k, v in p.items() if k.startswith(fp)}
    re_.case_id = p.get(prefix + "related.caseId", "")
    return re_


# ... convert_elastic_event_to_comment / _artifact / _artifact_stream / _detection /
#     _detection_comment / _override  (port the remaining converters analogously)


_DISPATCH = {
    "case": convert_elastic_event_to_case,
    "comment": None,            # convert_elastic_event_to_comment
    "related": convert_elastic_event_to_related_event,
    "artifact": None,
    "artifactstream": None,
    "detection": None,
    "detectioncomment": None,
}


def convert_elastic_event_to_object(rec, prefix: str):
    kind = rec.payload.get(prefix + "kind")
    if kind is None:
        return None, f"Unknown object kind; id={rec.id}"
    fn = _DISPATCH.get(kind)
    if fn is None:
        return None, None          # present-but-unrecognized -> (None, None)
    return fn(rec, prefix), None
```

> Split into two commits if it exceeds ~200 LOC: (9a) `convert_severity` + case/comment/related + dispatch; (9b) artifact/artifactstream/detection/detectioncomment/override. The detection converter reads flat `so_detection.*` keys but `overrides` come back **nested** — handle that asymmetry. Inject a `feat_ttr`/`feat_rpt` bool where the Go gates `comment.hours` etc. (default False).

**Step 4 — run green** · **Step 5 — ruff+mypy** · **Step 6 — commit**
```
feat(es): converter domain-object mappers + convert_severity + dispatch
```
(or two commits 9a/9b)

---

## TASK 10 — ElasticEventstore: search() (mocked client)

**Files**
- Create: `backend/src/adapters/elasticsearch/eventstore.py`
- Create test: `backend/tests/adapters/elasticsearch/test_eventstore_search.py`

**Step 1 — write failing test** (mock `AsyncElasticsearch`; assert it calls `search` with the built body + `track_total_hits` + `ignore_unavailable`, and maps the response)
```python
import json
from pathlib import Path
from unittest.mock import AsyncMock

from src.adapters.elasticsearch.config import ElasticConfig
from src.adapters.elasticsearch.client import ElasticClients
from src.adapters.elasticsearch.eventstore import ElasticEventstore
from src.domain.event import EventSearchCriteria
from src.domain.query import Query

FIX = Path(__file__).parent / "fixtures"


def _store(es) -> ElasticEventstore:
    return ElasticEventstore(ElasticClients(primary=es), ElasticConfig())


async def test_search_calls_es_and_maps_results():
    es = AsyncMock()
    es.field_caps.return_value = {"fields": {}}
    es.search.return_value = json.loads((FIX / "converter_response.json").read_text())
    store = _store(es)

    c = EventSearchCriteria()
    c.metric_limit = 0; c.event_limit = 25
    c.parsed_query = Query(); c.parsed_query.parse("*")
    res = await store.search(c)

    assert res.total_events == 23689430
    assert len(res.events) == 25
    es.search.assert_awaited_once()
    kwargs = es.search.await_args.kwargs
    assert kwargs["track_total_hits"] is True
    assert kwargs["ignore_unavailable"] is True
    assert kwargs["index"] == ["*:so-*"]
    assert res.criteria is c
    assert res.complete_time > res.create_time  # complete() called


async def test_search_timeout_sets_error():
    es = AsyncMock()
    es.field_caps.return_value = {"fields": {}}
    es.search.return_value = {"took": 5, "timed_out": True, "hits": {}}
    store = _store(es)
    c = EventSearchCriteria(); c.metric_limit = 0
    c.parsed_query = Query(); c.parsed_query.parse("*")
    res = await store.search(c)
    assert "Timeout" in res.errors[0]
```

> The `AsyncElasticsearch` 8.x client returns dict-like `ObjectApiResponse`; the mock returns a plain dict (compatible). If a later test needs `.body`, normalize via `dict(resp)` in the adapter.

**Step 2 — run to confirm red** → `ModuleNotFoundError`.

**Step 3 — minimal implementation**
```python
from __future__ import annotations

from src.adapters.elasticsearch.client import ElasticClients
from src.adapters.elasticsearch.config import ElasticConfig
from src.adapters.elasticsearch.converter import parse_search_results
from src.adapters.elasticsearch.field_caps import FieldCapsCache
from src.adapters.elasticsearch.query_builder import build_search_request
from src.domain.event import EventSearchCriteria, EventSearchResults


class ElasticEventstore:
    def __init__(self, clients: ElasticClients, config: ElasticConfig) -> None:
        self._clients = clients
        self._config = config
        self._cache = FieldCapsCache(config.cache_ms)

    @property
    def _indexes(self) -> list[str]:
        return self._config.index.split(",")

    async def _refresh_cache(self) -> None:
        async def fetch() -> dict:
            return dict(await self._clients.read_client.field_caps(
                index=self._indexes, fields="*"))
        await self._cache.refresh(fetch)

    async def search(self, criteria: EventSearchCriteria) -> EventSearchResults:
        results = EventSearchResults()
        await self._refresh_cache()
        body = build_search_request(self._cache.defs, self._config.intervals, criteria)
        resp = await self._clients.read_client.search(
            index=self._indexes, query=body.get("query"),
            aggs=body.get("aggs"), sort=body.get("sort"),
            size=body.get("size"), search_after=body.get("search_after"),
            track_total_hits=True, ignore_unavailable=True)
        err = parse_search_results(self._cache.defs, dict(resp), results)
        if err:
            results.errors.append(err)
        results.criteria = criteria
        results.complete()
        return results
```

> Decide one calling convention: either pass discrete kwargs (above) or `body=...`. The test asserts `track_total_hits`/`ignore_unavailable`/`index`; keep those. `build_search_request` now takes `(defs, intervals, criteria)` per Task 7 note.

**Step 4 — run green** · **Step 5 — ruff+mypy** · **Step 6 — commit**
```
feat(es): ElasticEventstore.search with field-caps cache (mocked-client tests)
```

---

## TASK 11 — ElasticEventstore: acknowledge() (script builders + update_by_query fan-out)

**Files**
- Modify: `backend/src/adapters/elasticsearch/eventstore.py`
- Create: `backend/src/adapters/elasticsearch/ack_scripts.py` (painless builders — verbatim text)
- Create test: `backend/tests/adapters/elasticsearch/test_ack_scripts.py`
- Create test: `backend/tests/adapters/elasticsearch/test_eventstore_acknowledge.py`

**Step 1 — write failing test**

`test_ack_scripts.py` (port `TestAddUpdateScript` — assert VERBATIM painless text):
```python
from src.adapters.elasticsearch.ack_scripts import build_acknowledge_script


def test_acknowledge_script_text_verbatim():
    scripts, params = build_acknowledge_script(now_millis=1700000000000,
                                              escalate=False, user_id="u1",
                                              track_timing=False)
    # PASTE the exact painless source asserted in elasticqueries_test.go TestAddUpdateScript
    assert scripts[0] == "<GO_VERBATIM_ACK_SCRIPT>"
    assert params["userId"] == "u1"
    assert params["nowMillis"] == 1700000000000
```

`test_eventstore_acknowledge.py`:
```python
from unittest.mock import AsyncMock

from src.adapters.elasticsearch.client import ElasticClients
from src.adapters.elasticsearch.config import ElasticConfig
from src.adapters.elasticsearch.eventstore import ElasticEventstore
from src.domain.event import EventAckCriteria


async def test_acknowledge_requires_event_filter():
    es = AsyncMock(); es.field_caps.return_value = {"fields": {}}
    store = ElasticEventstore(ElasticClients(primary=es), ElasticConfig(), requestor_id="u1")
    c = EventAckCriteria(); c.event_filter = {}
    res = await store.acknowledge(c)
    assert "EventFilter must be specified" in res.errors[0]
    es.update_by_query.assert_not_awaited()


async def test_acknowledge_fans_out_over_all_clients():
    es1, es2 = AsyncMock(), AsyncMock()
    for es in (es1, es2):
        es.field_caps.return_value = {"fields": {}}
        es.update_by_query.return_value = {"took": 10, "timed_out": False, "updated": 2, "noops": 1}
    store = ElasticEventstore(ElasticClients(primary=es1, remotes=[es2]),
                             ElasticConfig(), requestor_id="u1")
    c = EventAckCriteria(); c.acknowledge = True
    c.event_filter = {"event.module": "suricata"}
    res = await store.acknowledge(c)
    es1.update_by_query.assert_awaited_once()
    es2.update_by_query.assert_awaited_once()
    assert res.updated_count == 4 and res.unchanged_count == 2  # accumulated


async def test_acknowledge_zero_updates_message():
    es = AsyncMock(); es.field_caps.return_value = {"fields": {}}
    es.update_by_query.return_value = {"took": 1, "timed_out": False, "updated": 0, "noops": 0}
    store = ElasticEventstore(ElasticClients(primary=es), ElasticConfig(), requestor_id="u1")
    c = EventAckCriteria(); c.acknowledge = True; c.event_filter = {"k": "v"}
    res = await store.acknowledge(c)
    assert "No eligible events available to acknowledge" in res.errors
```

> Capture `<GO_VERBATIM_ACK_SCRIPT>` from `server/modules/elastic/elasticqueries_test.go` (`TestAddUpdateScript`). Port byte-for-byte including `ZoneId('Z')`, `ChronoUnit`, and FEAT_RPT-gated timing fields.

**Step 2 — run to confirm red** → `ModuleNotFoundError`.

**Step 3 — minimal implementation**

`ack_scripts.py` — port `addAcknowledgeScript`/`addUnacknowledgeScript` and return `(list[str], dict)` of source + params (verbatim text).

`eventstore.py` `acknowledge`:
```python
async def acknowledge(self, criteria) -> EventUpdateResults:
    results = EventUpdateResults()
    if not criteria.event_filter:
        results.errors.append("EventFilter must be specified to ack an event")
        return results
    uc = self._build_update_criteria_from_ack(criteria)  # builds parsed_query + scripts + async flag
    await self._update(uc, results)        # fan-out helper
    if not uc.asynchronous and not results.errors:
        if results.updated_count == 0:
            results.errors.append(
                "No eligible events available to acknowledge" if results.unchanged_count == 0
                else "All events have already been acknowledged")
    results.complete()
    return results

async def _update(self, criteria, results) -> None:
    await self._refresh_cache()
    body = build_update_request(self._cache.defs, criteria)
    errors = []
    for client in self._clients.all_clients:
        indexes = [disable_cross_cluster_index(i) for i in self._indexes]
        try:
            resp = await client.update_by_query(
                index=indexes, query=body["query"], script=body["script"],
                conflicts="proceed", refresh=True,
                wait_for_completion=not criteria.asynchronous)
            if not criteria.asynchronous:
                sub = EventUpdateResults()
                err = parse_update_results(dict(resp), sub)
                if err: errors.append(err)
                else: results.add_event_update_results(sub)
        except Exception as e:  # noqa: BLE001 — collect per-host
            errors.append(str(e))
    # partial success tolerated: only surface errors if ALL hosts failed
    if len(errors) >= len(self._clients.all_clients):
        results.errors.extend(errors)
```

> The `count` pseudo-field in `event_filter` toggles `asynchronous` when `> async_threshold` and is NOT added as a filter (Go behavior). `requestor_id` is a constructor arg (no ctx). Build the ack filter via `SearchSegment.add_filter` from `src/domain/query.py`.

**Step 4 — run green** · **Step 5 — ruff+mypy** · **Step 6 — commit**
```
feat(es): ElasticEventstore.acknowledge with painless ack scripts + update_by_query fan-out
```

---

## TASK 12 — ElasticEventstore: get_active_queries() + cancel_query() (tasks API)

**Files**
- Modify: `backend/src/adapters/elasticsearch/eventstore.py`
- Create: `backend/src/adapters/elasticsearch/tasks.py` (ElasticTask response model + `parse_query_tasks`)
- Create test: `backend/tests/adapters/elasticsearch/test_tasks.py`
- Create test: `backend/tests/adapters/elasticsearch/test_eventstore_tasks.py`

**Step 1 — write failing test** (port `convertFromElasticQueryTaskResults` cases + filter logic)
```python
from unittest.mock import AsyncMock

from src.adapters.elasticsearch.tasks import parse_query_tasks
from src.adapters.elasticsearch.client import ElasticClients
from src.adapters.elasticsearch.config import ElasticConfig
from src.adapters.elasticsearch.eventstore import ElasticEventstore

_TASKS = {"nodes": {"n1": {"tasks": {
    "n1:1": {"cancellable": True, "action": "indices:data/read/search",
             "type": "transport", "start_time_in_millis": 1700000000000,
             "running_time_in_nanos": 5_000_000, "parent_task_id": ""},
    "n1:2": {"cancellable": False, "action": "cluster:monitor/tasks/lists",
             "type": "transport", "start_time_in_millis": 1700000000000,
             "running_time_in_nanos": 1_000_000, "parent_task_id": ""},
}}}}


def test_parse_query_tasks_filter_excludes_noncancelable_and_listself():
    tasks = parse_query_tasks(_TASKS, client="C", grid_id="", filter_internal=True)
    assert [t.task_id for t in tasks] == ["n1:1"]
    assert tasks[0].cancelable is True
    assert tasks[0].elapsed_ms == 5  # nanos/1e6


def test_parse_query_tasks_no_filter_keeps_all():
    tasks = parse_query_tasks(_TASKS, client="C", grid_id="", filter_internal=False)
    assert len(tasks) == 2


async def test_get_active_queries_uses_tasks_list():
    es = AsyncMock(); es.tasks.list.return_value = _TASKS
    store = ElasticEventstore(ElasticClients(primary=es), ElasticConfig())
    tasks = await store.get_active_queries(True)
    assert len(tasks) == 1
    es.tasks.list.assert_awaited_once()


async def test_cancel_query_finds_task_and_cancels_on_its_client():
    es = AsyncMock(); es.tasks.list.return_value = _TASKS
    store = ElasticEventstore(ElasticClients(primary=es), ElasticConfig())
    await store.cancel_query("n1:1")
    es.tasks.cancel.assert_awaited_once_with(task_id="n1:1")


async def test_cancel_query_not_found_raises():
    es = AsyncMock(); es.tasks.list.return_value = {"nodes": {}}
    store = ElasticEventstore(ElasticClients(primary=es), ElasticConfig())
    import pytest
    with pytest.raises(Exception, match="query not found"):
        await store.cancel_query("missing")
```

> **Decision:** FIX the Go latent bug — iterate over each client and call `client.tasks.list()` on the loop variable (not the primary). Track which client each task came from so `cancel_query` cancels on the owning client (multi-cluster correctness). Document this divergence in the module docstring.

**Step 2 — run to confirm red** → `ModuleNotFoundError`.

**Step 3 — minimal implementation**

`tasks.py`: `parse_query_tasks(body, client, grid_id, filter_internal)` → `list[QueryTask]` where each `QueryTask` (from `src.ports.events`) carries the originating client (attach as an attribute, e.g. `task._client = client`). Filter excludes when `not cancellable` OR `type == "persistent"` OR `parent_task_id` non-empty OR `action == "cluster:monitor/tasks/lists"`. `details = f"{type} ({action})"`, `elapsed_ms = running_time_in_nanos // 1_000_000`.

`eventstore.py`:
```python
async def get_active_queries(self, filter_internal: bool) -> list[QueryTask]:
    out: list[QueryTask] = []
    for client in self._clients.all_clients:
        body = dict(await client.tasks.list())
        out.extend(parse_query_tasks(body, client, "", filter_internal))
    return out

async def cancel_query(self, query_id: str) -> None:
    for task in await self.get_active_queries(False):
        if task.task_id == query_id:
            await task._client.tasks.cancel(task_id=query_id)
            return
    raise RuntimeError("query not found")
```

**Step 4 — run green** · **Step 5 — ruff+mypy** · **Step 6 — commit**
```
feat(es): ElasticEventstore.get_active_queries + cancel_query (tasks API, bug fixed)
```

---

## TASK 13 — Shared store base: index/delete/search-back + audit dual-write + ConvertObjectToDocumentMap

The case/detection/assistant stores all share: build a `{prefix+kind: obj, '@timestamp': now, prefix+'kind': kind}` document, index it (refresh=true), and write an audit snapshot. Factor this once.

**Files**
- Create: `backend/src/adapters/elasticsearch/store_base.py`
- Modify: `backend/src/adapters/elasticsearch/converter.py` (add `convert_object_to_document_map`)
- Create test: `backend/tests/adapters/elasticsearch/test_store_base.py`

**Step 1 — write failing test**
```python
from unittest.mock import AsyncMock

from src.adapters.elasticsearch.converter import convert_object_to_document_map
from src.adapters.elasticsearch.store_base import index_document, save_with_audit


def test_convert_object_to_document_map():
    doc = convert_object_to_document_map("test", {"a": 1}, "so_")
    assert doc["so_test"] == {"a": 1}
    assert "@timestamp" in doc


async def test_index_document_refresh_true():
    es = AsyncMock(); es.index.return_value = {"_id": "x1", "result": "created"}
    r = await index_document(es, "*:so-case", {"so_kind": "case"}, "abc12")
    assert r.document_id == "x1" and r.success is True
    kwargs = es.index.await_args.kwargs
    assert kwargs["refresh"] == "true"
    assert kwargs["index"] == "so-case"   # cross-cluster prefix stripped on write
    assert kwargs["id"] == "abc12"


async def test_save_with_audit_writes_two_docs():
    es = AsyncMock(); es.index.return_value = {"_id": "live1", "result": "created"}
    result = await save_with_audit(es, index="*:so-case", audit_index="*:so-casehistory",
                                  document={"so_kind": "case"}, doc_id="", prefix="so_")
    assert es.index.await_count == 2
    # second call -> audit index with operation=create and audit_doc_id=live1
    audit_kwargs = es.index.await_args_list[1].kwargs
    assert audit_kwargs["index"] == "so-casehistory"
    assert audit_kwargs["document"]["so_operation"] == "create"
    assert audit_kwargs["document"]["so_audit_doc_id"] == "live1"
```

**Step 2 — run to confirm red** → `ModuleNotFoundError`.

**Step 3 — minimal implementation** (`index_document`, `delete_document`, `save_with_audit`, `delete_with_audit`). `save_with_audit`: index live doc → on success set `prefix+audit_doc_id`, `prefix+operation` (`create` if `doc_id==""` else `update`), index into audit index with empty id; audit failure logged not raised.

**Step 4 — run green** · **Step 5 — ruff+mypy** · **Step 6 — commit**
```
feat(es): shared store base (index/delete + dual-write audit + doc-map)
```

---

## TASK 14 — ElasticCasestore: case CRUD + history

**Files**
- Create: `backend/src/adapters/elasticsearch/casestore.py`
- Create test: `backend/tests/adapters/elasticsearch/test_casestore_case.py`

**Step 1 — write failing test** (port relevant `elasticcasestore_test.go` cases — validation error strings, read-after-write, audit, history query)
```python
from unittest.mock import AsyncMock
import pytest

from src.adapters.elasticsearch.client import ElasticClients
from src.adapters.elasticsearch.config import ElasticConfig
from src.adapters.elasticsearch.casestore import ElasticCasestore
from src.domain.case import Case


def _store(es):
    return ElasticCasestore(ElasticClients(primary=es), ElasticConfig(), requestor_id="u1")


async def test_create_rejects_supplied_id():
    es = AsyncMock()
    case = Case(); case.id = "abc12"; case.title = "T"; case.status = "x"; case.description = "d"
    with pytest.raises(Exception, match="invalid ID for caseId"):
        await _store(es).create(case)


async def test_create_indexes_live_and_audit_then_reads_back():
    es = AsyncMock()
    es.index.return_value = {"_id": "live1", "result": "created"}
    # read-back search returns the created case
    es.search.return_value = {"took": 1, "timed_out": False, "hits": {"total": 1, "hits": [
        {"_index": "so-case", "_id": "live1",
         "_source": {"so_kind": "case", "so_case": {"title": "T", "status": "new"}}}]}}
    case = Case(); case.title = "T"; case.status = "x"; case.description = "d"
    created = await _store(es).create(case)
    assert created.id == "live1"
    assert es.index.await_count == 2          # live + audit
    # Status forced to 'new' on create
    assert created.status == "new"


async def test_get_case_invalid_id():
    es = AsyncMock()
    with pytest.raises(Exception, match="invalid ID for caseId"):
        await _store(es).get_case("ab")       # too short
```

> Port the exact error strings the Go tests pin: `"invalid ID for caseId"`, `"Unexpected ID found in new case"`, `"Missing case ID"`, `"Object not found"`, `"title is too long (140/100)"`, the severity mutation, status workflow side-effects. Split into 14a (create/update/get + validate_case) and 14b (get_case_history) if > ~200 LOC.

**Step 2 — run to confirm red** → `ModuleNotFoundError`.

**Step 3 — minimal implementation** — `ElasticCasestore` with: `validate_id` (reuse escaping), `validate_case`, `_save`/`_get`/`_get_all` (Lucene query strings: `_index:"<index>" AND so_kind:"<kind>" AND _id:"<escape_lucene(id)>"`), `create`/`update`/`get_case`/`get_case_history`. `_get_all` builds an `EventSearchCriteria`, runs `search()` via an internal eventstore-style search, converts each record via `convert_elastic_event_to_object`. Reads use the full cross-cluster index; writes strip it (via store_base).

> The casestore needs a `search` path. Reuse the same `_refresh_cache`+`build_search_request`+`parse_search_results` flow — either compose an `ElasticEventstore` instance internally or extract a shared `_search(query_str, limit)` helper. Prefer composition: `ElasticCasestore(clients, config, requestor_id, eventstore=ElasticEventstore(...))`.

**Step 4 — run green** · **Step 5 — ruff+mypy** · **Step 6 — commit**
```
feat(es): ElasticCasestore case CRUD + history with audit dual-write
```

---

## TASK 15 — ElasticCasestore: comments + related events + artifacts + artifact streams + observables

Split into sub-tasks to stay < ~200 LOC each:

### 15a — Comments + observables classifier
**Files**: modify `casestore.py`; create `observables.py`; tests `test_casestore_comments.py`, `test_observables.py`.

**Step 1 test** — port `observables_test.go` (`GetType` order ip/domain/fqdn/url/filename/uriPath/hash, default `other`; IP via `ipaddress`) and comment CRUD (`create_comment`/`get_comment`/`get_comments`/`update_comment`/`delete_comment`, `"Missing comment ID"`, `"Unexpected ID found in new comment"`, `"Missing Case ID in new comment"`, createTime-preserve on update, sortby `so_comment.createTime^`).

**Step 3 impl** — `Observables.get_type` with `ipaddress.ip_address` for IP + the exact regexes from recon; comment methods mirroring case methods (`kind="comment"`).

**Commit:** `feat(es): casestore comments + observables classifier`

### 15b — Related events (bulk create + manual sort) + ExtractCommonObservables
**Files**: modify `casestore.py`; test `test_casestore_related.py`.

**Step 1 test** — `create_related_events` returns `(total_created, err_map, fatal)`; duplicate → `"ERROR_CASE_EVENT_ALREADY_ATTACHED"`; `get_related_events` manual in-memory sort by `fields["timestamp"]` with missing-timestamp-first; `"Related event fields cannot not be empty"` (preserve typo). Use a serial awaited loop in place of the Go BulkIndexer (or `elasticsearch.helpers.async_bulk` with `refresh="wait_for"`).

**Step 3 impl** — port `CreateRelatedEvents` (group by case, cap at `MaxBulkEscalateEvents`, dup check via existing soc_id set, inline observable extraction swallowing errors) + `get_related_events` + `delete_related_event` + `ExtractCommonObservables` (returns error variant).

**Commit:** `feat(es): casestore related events (bulk) + observable extraction`

### 15c — Artifacts + artifact streams
**Files**: modify `casestore.py`; test `test_casestore_artifacts.py`.

**Step 1 test** — `create_artifact` (`validate_artifact` ordering: value before groupType, `"invalid ID for groupType"`), `update_artifact` preserves the many immutable fields (only Description/Tlp/Tags/Ioc/Protected mutable), `get_artifacts(case_id, group_type, group_id)`, `create_artifact_stream` returns `str` id (no read-back), `get_case_ids_with_artifact` (free-text → `escape_lucene`, unique CaseId first-seen order), `delete_artifact` cascade (stream + analyzer-job hook is a no-op injected dependency).

**Step 3 impl** — port artifact/artifactstream methods + `GetCaseIdsWithArtifact`.

**Commit:** `feat(es): casestore artifacts + artifact streams + case-ids-with-artifact`

---

## TASK 16 — ElasticDetectionstore: detection CRUD + get-by-public-id + history + template existence

**Files**
- Create: `backend/src/adapters/elasticsearch/detectionstore.py`
- Create test: `backend/tests/adapters/elasticsearch/test_detectionstore.py`

**Step 1 — write failing test** (port `elasticdetectionstore_test.go` cases)
```python
from unittest.mock import AsyncMock
import pytest

from src.adapters.elasticsearch.client import ElasticClients
from src.adapters.elasticsearch.config import ElasticConfig
from src.adapters.elasticsearch.detectionstore import ElasticDetectionstore
from src.domain.detection import Detection


def _store(es):
    return ElasticDetectionstore(ElasticClients(primary=es), ElasticConfig(), requestor_id="u1")


async def test_create_duplicate_public_id_raises_already_exists():
    es = AsyncMock()
    # dup-check search returns a hit
    es.search.return_value = {"took": 1, "timed_out": False, "hits": {"total": 1, "hits": [
        {"_index": "so-detection", "_id": "d1",
         "_source": {"so_kind": "detection", "so_detection": {"publicId": "100", "engine": "suricata"}}}]}}
    det = Detection(); det.public_id = "100"; det.engine = "suricata"; det.language = "suricata"
    det.title = "t"; det.author = "a"; det.description = "d"; det.content = "c"; det.severity = "high"
    with pytest.raises(Exception, match="already exists"):
        await _store(es).create_detection(det)


async def test_create_detection_sets_deterministic_uuid_id():
    from src.adapters.elasticsearch.escaping import to_uuid
    es = AsyncMock()
    es.search.side_effect = [
        {"took": 1, "timed_out": False, "hits": {"total": 0, "hits": []}},  # dup-check empty
        {"took": 1, "timed_out": False, "hits": {"total": 1, "hits": [     # read-back
            {"_index": "so-detection", "_id": to_uuid("100"),
             "_source": {"so_kind": "detection", "so_detection": {"publicId": "100", "engine": "suricata"}}}]}},
    ]
    es.index.return_value = {"_id": to_uuid("100"), "result": "created"}
    det = Detection(); det.public_id = "100"; det.engine = "suricata"; det.language = "suricata"
    det.title = "t"; det.author = "a"; det.description = "d"; det.content = "c"; det.severity = "high"
    created = await _store(es).create_detection(det)
    assert created.id == to_uuid("100")


async def test_does_template_exist_404_false():
    from elasticsearch import NotFoundError
    es = AsyncMock()
    es.indices.get_index_template.side_effect = NotFoundError("m", meta=None, body=None)
    assert await _store(es).does_template_exist("myTemplate") is False
```

> Engine/language are always validated (`"invalid engine"`, `"invalid language"`, `"engine and language mismatch"`). `id = to_uuid(public_id)`. History query targets the audit index, uses `escape_lucene` only (no `validate_id`). `Query(max==-1)` → scroll path: implement a `_scroll(query_str)` helper (es.search(scroll='1m') + es.scroll + es.clear_scroll, ignore 404 on clear). Split 16a (CRUD + get-by-public-id + template) / 16b (history + get_all_detections scroll) if > ~200 LOC.

**Step 2 — run to confirm red** → `ModuleNotFoundError`.

**Step 3 — minimal implementation** — port detection methods; reuse store_base + the casestore-style `_get`/`_get_all`/composition with eventstore. `does_template_exist` catches `elasticsearch.NotFoundError` → `False`.

**Step 4 — run green** · **Step 5 — ruff+mypy** · **Step 6 — commit**
```
feat(es): ElasticDetectionstore CRUD + public-id + history + template existence
```

---

## TASK 17 — ElasticDetectionstore: comments

**Files**
- Modify: `backend/src/adapters/elasticsearch/detectionstore.py`
- Create test: `backend/tests/adapters/elasticsearch/test_detectionstore_comments.py`

**Step 1 — write failing test** — `create_comment` (`validate_comment`, requires Value min 1, `"Unexpected ID found in new comment"`, `"Missing Detection ID in new comment"`, parent `get_detection` check), `get_comment`, `get_comments` (sortby `so_detectioncomment.createTime^`, `validate_id` on `detection_id`), `update_comment` (createTime preserve, `"Missing comment ID"`), `delete_comment` (2 ES requests: delete + audit).

**Step 2 — run to confirm red** → fails on missing methods.

**Step 3 — minimal implementation** — port the four detection-comment methods (`kind="detectioncomment"`).

**Step 4 — run green** · **Step 5 — ruff+mypy** · **Step 6 — commit**
```
feat(es): ElasticDetectionstore comments
```

---

## TASK 18 — ElasticAssistantstore: sessions + chat history

**Files**
- Create: `backend/src/adapters/elasticsearch/assistantstore.py`
- Create test: `backend/tests/adapters/elasticsearch/test_assistantstore.py`

**Step 1 — write failing test** (port `elasticassistantstore_test.go` — validation, storage shape, soft delete, session filtering)
```python
from datetime import datetime, timezone
from unittest.mock import AsyncMock
import pytest

from src.adapters.elasticsearch.client import ElasticClients
from src.adapters.elasticsearch.config import ElasticConfig
from src.adapters.elasticsearch.assistantstore import ElasticAssistantstore
from src.domain.assistant import AssistantSession, GetSessionsQuery, Message, StoredMessage


def _store(es):
    return ElasticAssistantstore(ElasticClients(primary=es), ElasticConfig(), requestor_id="u1")


async def test_save_chat_validates_session_id():
    es = AsyncMock()
    msg = StoredMessage(); msg.session_id = "ab"  # too short
    m = Message(); m.content_str = "hi"; msg.message = m
    with pytest.raises(Exception, match="invalid ID for SessionId"):
        await _store(es).save_chat(msg)


async def test_save_chat_indexes_storage_shaped_doc():
    es = AsyncMock(); es.index.return_value = {"_id": "c1", "result": "created"}
    msg = StoredMessage(); msg.session_id = "session_12345"
    m = Message(); m.role = "user"; m.content_str = "hello"; msg.message = m
    await _store(es).save_chat(msg)
    doc = es.index.await_args.kwargs["document"]
    assert doc["so_kind"] == "chat"
    # storage shape: contentStr (NOT content), under so_chat.message
    assert doc["so_chat"]["message"]["contentStr"] == "hello"


async def test_delete_session_is_soft_delete_via_update_by_query():
    es = AsyncMock()
    await _store(es).delete_session("session_12345")
    es.update_by_query.assert_awaited_once()
    body = es.update_by_query.await_args.kwargs
    assert "deleteTime" in body["script"]["source"]


async def test_get_sessions_excludes_deleted_by_default():
    es = AsyncMock()
    es.search.return_value = {"took": 1, "timed_out": False, "hits": {"total": 0, "hits": []}}
    es.msearch.return_value = {"took": 1, "responses": []}
    await _store(es).get_sessions(GetSessionsQuery(include_deleted=False))
    body = es.search.await_args.kwargs
    # must_not exists deleteTime present
    must_not = body["query"]["bool"]["must_not"]
    assert any("deleteTime" in str(c) for c in must_not)
```

> `StoredMessage`/`Message` storage shape MUST use the camelCase storage keys (`contentStr`, `contentBlocks`, `stopReason`, `stopSequence`) via `Message.model_dump`/`prepare_for_storage`, NOT the LLM-API keys (`content`, `stop_reason`). Authorization is per-session in Go (`filterSharedSessions`); since the Python ports have no ctx + no CheckAuthorized, **drop** the authz filtering (record as divergence) — keep the rest (soft-delete filter, range, ordering, partial-malformed-hit skipping). Split 18a (save_chat/get_chat_history/create_session/get_sessions core) / 18b (usage enrichment msearch + UpdateSessionTags/DeleteSession) if > ~200 LOC.

**Step 2 — run to confirm red** → `ModuleNotFoundError`.

**Step 3 — minimal implementation** — port `save_chat`, `get_chat_history` (must return `[]` for unknown session OR raise with `"not found"` in the message — service tolerance contract), `create_session`, `get_sessions` (term filters + must_not exists deleteTime + range + sort @timestamp asc + size 10000 + partial-hit skip), `update_session_tags` (owner-scoped update_by_query painless replace), `delete_session` (soft delete via painless `deleteTime`). Storage doc envelope `{prefix+kind: body, "@timestamp": now, prefix+"kind": kind}`.

**Step 4 — run green** · **Step 5 — ruff+mypy** · **Step 6 — commit**
```
feat(es): ElasticAssistantstore sessions + chat history (storage-shaped messages, soft delete)
```

---

## TASK 19 — ElasticAssistantstore: usage aggregations (populate_session_usage, get_usage)

**Files**
- Modify: `backend/src/adapters/elasticsearch/assistantstore.py`
- Create test: `backend/tests/adapters/elasticsearch/test_assistantstore_usage.py`

**Step 1 — write failing test** — `get_usage(start, end)` returns `list[UserUsage]` from a single size-0 aggregation search (terms on `so_chat.userId`, sums on usage fields, cardinality on sessionId, nested model_usage terms); aggregation floats → int truncation; empty model bucket key skipped. `get_sessions(with_usage=True)` runs an msearch and attaches `SessionUsage` positionally; per-response `error` key → leave usage None; `addMetaFromMessages` sets `update_time` from `value_as_string` max(createTime).

**Step 2 — run to confirm red** → fails on missing usage logic.

**Step 3 — minimal implementation** — build the aggregation bodies exactly per recon; positional msearch alignment `responses[i] <-> sessions[i]`; cast `.value` floats to int.

**Step 4 — run green** · **Step 5 — ruff+mypy** · **Step 6 — commit**
```
feat(es): ElasticAssistantstore usage aggregations (session + user)
```

---

## TASK 20 — docker-compose.dev.yml + integration tests (skippable when ES absent)

**Files**
- Create: `backend/docker-compose.dev.yml` (single-node ES 8.x, `discovery.type=single-node`, `xpack.security.enabled=false`, port 9200)
- Create: `backend/tests/adapters/elasticsearch/integration/__init__.py`
- Create: `backend/tests/adapters/elasticsearch/integration/conftest.py` (skip marker + real client fixture)
- Create: `backend/tests/adapters/elasticsearch/integration/test_eventstore_integration.py`
- Create: `backend/tests/adapters/elasticsearch/integration/test_casestore_integration.py`

**Step 1 — write failing test** — a real round-trip: index a doc into a temp index, `search()` it back, assert mapping. Guard with:
```python
import os
import pytest
from elasticsearch import AsyncElasticsearch

ES_URL = os.environ.get("ES_TEST_URL", "http://localhost:9200")


def _es_available() -> bool:
    import socket, urllib.parse
    u = urllib.parse.urlparse(ES_URL)
    try:
        with socket.create_connection((u.hostname, u.port or 9200), timeout=0.5):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _es_available(), reason="no live Elasticsearch")


@pytest.fixture
async def real_es():
    es = AsyncElasticsearch(hosts=[ES_URL], verify_certs=False, ssl_show_warn=False)
    yield es
    await es.close()


async def test_index_then_search_roundtrip(real_es):
    from src.adapters.elasticsearch.eventstore import ElasticEventstore
    from src.adapters.elasticsearch.client import ElasticClients
    from src.adapters.elasticsearch.config import ElasticConfig
    from src.domain.event import EventSearchCriteria
    from src.domain.query import Query

    idx = "so-itest-events"
    await real_es.index(index=idx, document={"@timestamp": "2020-01-01T00:00:00.000Z", "event": {"module": "test"}}, refresh="true")
    cfg = ElasticConfig(index=idx)
    store = ElasticEventstore(ElasticClients(primary=real_es), cfg)
    c = EventSearchCriteria(); c.metric_limit = 0; c.event_limit = 25
    c.parsed_query = Query(); c.parsed_query.parse("event.module:test")
    res = await store.search(c)
    assert res.total_events >= 1
    await real_es.indices.delete(index=idx, ignore_unavailable=True)
```

**Step 2 — run to confirm red** (with ES down → all skip; with ES up → red until impl is correct)
```
.venv/bin/python -m pytest tests/adapters/elasticsearch/integration -v
```
Expected (ES down): `SKIPPED`. To run for real: `docker compose -f backend/docker-compose.dev.yml up -d` then re-run.

**Step 3 — minimal implementation** — write `docker-compose.dev.yml`; the adapter code already exists. Add a short README note in the compose file header on usage.

**Step 4 — run green** — `docker compose -f backend/docker-compose.dev.yml up -d`, wait for health, run integration tests; then verify they SKIP cleanly when ES is down.

**Step 5 — ruff+mypy** — lint/type the integration test files.

**Step 6 — commit**
```
test(es): docker-compose.dev ES + skippable integration tests
```

---

## TASK 21 — Wire stores into create_app + wiring test

**Files**
- Modify: `backend/src/main.py` (`create_app`)
- Modify: `backend/tests/test_wiring.py` (add ES-wiring test using `dependency_overrides`)

**Step 1 — write failing test** — assert that when ES config is present, the events/case/detection/assistant route service dependencies resolve to services backed by the ES adapter. Because ES isn't reachable in unit tests, wire with `dependency_overrides` and assert the override is installed + the adapter type, WITHOUT making network calls:
```python
async def test_create_app_wires_elasticsearch_stores(tmp_path):
    import json
    from src.main import create_app
    from src.api import events_routes

    config = {"server": {"modules": {
        "statickeyauth": {"apiKey": "k", "anonymousCidr": "*"},
        "filedatastore": {"jobDir": str(tmp_path / "jobs")},
        "elastic": {"hostUrl": "http://localhost:9200", "index": "*:so-*"},
    }}}
    path = tmp_path / "sensoroni.json"; path.write_text(json.dumps(config))

    app = create_app(str(path))
    # EventsService dependency override is installed and backed by ElasticEventstore
    assert events_routes.get_events_service in app.dependency_overrides
    svc = app.dependency_overrides[events_routes.get_events_service]()
    from src.adapters.elasticsearch.eventstore import ElasticEventstore
    assert isinstance(svc.store, ElasticEventstore)


async def test_create_app_without_elastic_config_still_boots():
    from src.main import create_app
    app = create_app()
    assert app is not None
```

> Confirm the events route exposes `get_events_service` (it does: `src/api/events_routes.py`). For case/detection/assistant, check whether their route modules expose service-dependency hooks (`get_case_service`, etc.); wire each that exists. If a route module lacks a hook, note it and wire only events first (keep the task < 200 LOC; add the others in a follow-up if needed).

**Step 2 — run to confirm red** → `AssertionError` (override not installed) or `AttributeError`.

**Step 3 — minimal implementation** — in `create_app`, after Tier-1 wiring, add an ES section:
```python
from src.adapters.elasticsearch.client import ElasticClients, build_async_client
from src.adapters.elasticsearch.config import ElasticConfig
from src.adapters.elasticsearch.eventstore import ElasticEventstore
# (+ casestore/detectionstore/assistantstore as available)

es_cfg = cfg.elastic  # add ElasticConfig parsing into AppConfig (see note)
if es_cfg and es_cfg.host_url:
    primary = build_async_client(es_cfg.host_url, es_cfg.username, es_cfg.password,
                                verify_cert=es_cfg.verify_cert, timeout_ms=es_cfg.timeout_ms)
    remotes = [build_async_client(h, es_cfg.username, es_cfg.password,
                                 verify_cert=es_cfg.verify_cert, timeout_ms=es_cfg.timeout_ms)
               for h in es_cfg.remote_host_urls]
    clients = ElasticClients(primary=primary, remotes=remotes)
    application.router.on_shutdown.append(primary.close)
    for r in remotes:
        application.router.on_shutdown.append(r.close)
    eventstore = ElasticEventstore(clients, es_cfg)
    application.dependency_overrides[events_routes.get_events_service] = (
        lambda: EventsService(eventstore))
    application.dependency_overrides[events_routes.get_request_context_dep] = auth
    # ... case/detection/assistant service overrides where hooks exist
```

> Add `elastic: ElasticConfig` parsing to `src/config.py`/`AppConfig` (read `server.modules.elastic`, map camelCase JSON keys → snake_case via an explicit mapping, mirroring how `statickeyauth`/`filedatastore` are parsed). Keep it absent-safe (`None` when the module block is missing). Verify `EventsService.__init__(store)` attribute name is `store` (adjust the test/impl accordingly).

**Step 4 — run green** — `.venv/bin/python -m pytest tests/test_wiring.py -v`

**Step 5 — ruff+mypy** — `src/main.py`, `src/config.py`, `tests/test_wiring.py`

**Step 6 — commit**
```
feat(es): wire Elasticsearch stores into create_app (events + available routes)
```

---

## Run order

Execute strictly in sequence; each task ends green + committed before the next starts:

1. Task 1 — dep + config + client/transport
2. Task 2 — escaping + id helpers (`to_uuid` golden!)
3. Task 3 — generic helpers
4. Task 4 — field-caps cache + map/unmap
5. Task 5 — `make_query` + format/map search
6. Task 6 — `calc_timeline_interval` + build search/scroll/msearch/update
7. Task 7 — aggregations + sortby segment
8. Task 8 — response mapping (flatten/parse_*)
9. Task 9 — domain-object converters (9a/9b)
10. Task 10 — Eventstore.search
11. Task 11 — Eventstore.acknowledge + ack scripts
12. Task 12 — Eventstore.get_active_queries + cancel_query
13. Task 13 — shared store base (dual-write audit)
14. Task 14 — Casestore case CRUD + history (14a/14b)
15. Task 15 — Casestore comments/related/artifacts (15a/15b/15c)
16. Task 16 — Detectionstore CRUD + public-id + history + template (16a/16b)
17. Task 17 — Detectionstore comments
18. Task 18 — Assistantstore sessions + chat history (18a/18b)
19. Task 19 — Assistantstore usage aggregations
20. Task 20 — docker-compose + integration tests
21. Task 21 — wire into create_app + wiring test

Tasks 2–9 are pure and independent of each other except for stated imports — they could be parallelized, but keep them sequential for the review loop. Tasks 10–19 each depend on the pure layer (2–9) and store_base (13).

## Verification checklist

Run after each task AND as a final gate after Task 21 (all from `backend/`):

- [ ] **New adapter unit tests pass:** `.venv/bin/python -m pytest tests/adapters/elasticsearch -v` (excluding `integration/` when ES is down — those SKIP, not fail).
- [ ] **Integration tests SKIP cleanly with ES absent** and PASS with `docker compose -f docker-compose.dev.yml up -d`: `.venv/bin/python -m pytest tests/adapters/elasticsearch/integration -v`.
- [ ] **All pre-existing tests still pass:** `.venv/bin/python -m pytest -v` (full suite green).
- [ ] **Wiring test passes:** `.venv/bin/python -m pytest tests/test_wiring.py -v`.
- [ ] **Ruff clean** on the whole adapter + tests: `.venv/bin/python -m ruff check src/adapters/elasticsearch tests/adapters/elasticsearch`.
- [ ] **mypy introduces NO NEW errors:** `.venv/bin/python -m mypy src/adapters/elasticsearch` (the accepted pre-existing pydantic `User(...)` call-arg errors elsewhere are untouched).
- [ ] **Byte-equality** holds for every ported converter test (`json.dumps(..., sort_keys=True)` matches the Go `expectedJson` strings captured from `converter_test.go`).
- [ ] **`to_uuid` matches the Go golden value** (Task 2) — detection IDs are stable.
- [ ] **Painless ack/investigate script text is verbatim** vs `elasticqueries_test.go` (Task 11).
- [ ] **Security invariants preserved:** `validate_id`/`validate_public_id` run before any ES call in id-shaped paths; free-text values are `escape_lucene`-escaped; painless `userId`/`sessionId` passed only as params; MSearch index in header is JSON-encoded (not interpolated).
- [ ] **Characterization replay improves:** the recorded `/api/events` (and case/detection/assistant) characterization tests in `tests/characterization/` now exercise the ES-backed services without regression (run `.venv/bin/python -m pytest tests/characterization -v`).
- [ ] **Documented divergences from Go** (record in the adapter package docstring): no `CheckAuthorized` inside stores (auth at route layer); no `es-security-runas-user` header; `get_active_queries` uses the loop's client (Go bug fixed); assistant per-session authz filtering dropped.
- [ ] **Completion self-audit:** re-read the four ports in `src/ports/` and confirm every method is implemented with the exact signature and return type; confirm no module-level `app` was mutated; confirm `elasticsearch[async]` is in `pyproject.toml` `[project].dependencies` (not just dev).
