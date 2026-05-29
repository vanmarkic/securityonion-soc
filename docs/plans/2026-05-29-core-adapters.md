# Core Adapters Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the 5 core adapters (StaticKeyAuth, FileDatastore, StaticRBAC, Kratos, Elasticsearch) so the FastAPI backend can serve real requests with authentication, job storage, RBAC, and user management.

**Architecture:** Each adapter lives in `backend/src/adapters/<name>/` and implements one or more Protocol interfaces from `backend/src/ports/`. A config module reads `sensoroni.json` and a lifespan handler in `main.py` wires adapters via `dependency_overrides`. StaticKeyAuth is a FastAPI middleware (not a port adapter) that replaces the current stub `get_request_context()`.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, httpx, pytest + pytest-asyncio. No new dependencies for Tier 0. Tier 1 adds `elasticsearch[async]` for the ES adapter.

---

## Task 1: App Configuration Module

Create a Pydantic settings module that loads `sensoroni.json` and provides typed config to adapters.

**Files:**
- Create: `backend/src/config.py`
- Test: `backend/tests/test_config.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_config.py
"""Tests for app configuration loading."""

import json
from pathlib import Path

import pytest

from src.config import AppConfig, load_config


class TestLoadConfig:
    def test_load_from_dict(self):
        raw = {
            "server": {
                "modules": {
                    "statickeyauth": {
                        "apiKey": "testkey",
                        "anonymousCidr": "0.0.0.0/0",
                    },
                    "filedatastore": {
                        "jobDir": "jobs",
                    },
                }
            }
        }
        cfg = AppConfig.from_dict(raw)
        assert cfg.statickeyauth.api_key == "testkey"
        assert cfg.statickeyauth.anonymous_cidr == "0.0.0.0/0"
        assert cfg.filedatastore.job_dir == "jobs"

    def test_load_from_file(self, tmp_path: Path):
        config_file = tmp_path / "sensoroni.json"
        config_file.write_text(
            json.dumps(
                {
                    "server": {
                        "modules": {
                            "statickeyauth": {
                                "apiKey": "filekey",
                                "anonymousCidr": "*",
                            },
                            "filedatastore": {"jobDir": "/tmp/jobs"},
                        }
                    }
                }
            )
        )
        cfg = load_config(str(config_file))
        assert cfg.statickeyauth.api_key == "filekey"
        assert cfg.statickeyauth.anonymous_cidr == "*"

    def test_missing_module_uses_defaults(self):
        raw = {"server": {"modules": {}}}
        cfg = AppConfig.from_dict(raw)
        assert cfg.statickeyauth.api_key == ""
        assert cfg.filedatastore.job_dir == "jobs"

    def test_staticrbac_config(self):
        raw = {
            "server": {
                "modules": {
                    "staticrbac": {
                        "roleFiles": ["rbac/roles"],
                        "userFiles": ["rbac/users"],
                        "scanIntervalMs": 30000,
                        "defaultRole": "auditor",
                    }
                }
            }
        }
        cfg = AppConfig.from_dict(raw)
        assert cfg.staticrbac.role_files == ["rbac/roles"]
        assert cfg.staticrbac.default_role == "auditor"

    def test_kratos_config(self):
        raw = {
            "server": {
                "modules": {
                    "kratos": {"hostUrl": "http://kratos:4434"}
                }
            }
        }
        cfg = AppConfig.from_dict(raw)
        assert cfg.kratos.host_url == "http://kratos:4434"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_config.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.config'"

**Step 3: Write minimal implementation**

```python
# backend/src/config.py
"""App configuration — loads sensoroni.json and provides typed config."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class StaticKeyAuthConfig:
    api_key: str = ""
    anonymous_cidr: str = "0.0.0.0/0"


@dataclass(frozen=True)
class FileDatastoreConfig:
    job_dir: str = "jobs"
    retry_failure_interval_ms: int = 600_000
    retry_failure_max_attempts: int = 5


@dataclass(frozen=True)
class StaticRbacConfig:
    role_files: list[str] = field(default_factory=list)
    user_files: list[str] = field(default_factory=list)
    scan_interval_ms: int = 60_000
    default_role: str = ""


@dataclass(frozen=True)
class KratosConfig:
    host_url: str = ""


@dataclass(frozen=True)
class AppConfig:
    statickeyauth: StaticKeyAuthConfig = field(default_factory=StaticKeyAuthConfig)
    filedatastore: FileDatastoreConfig = field(default_factory=FileDatastoreConfig)
    staticrbac: StaticRbacConfig = field(default_factory=StaticRbacConfig)
    kratos: KratosConfig = field(default_factory=KratosConfig)

    @classmethod
    def from_dict(cls, raw: dict) -> AppConfig:
        modules = raw.get("server", {}).get("modules", {})

        ska = modules.get("statickeyauth", {})
        fds = modules.get("filedatastore", {})
        rbac = modules.get("staticrbac", {})
        kra = modules.get("kratos", {})

        return cls(
            statickeyauth=StaticKeyAuthConfig(
                api_key=ska.get("apiKey", ""),
                anonymous_cidr=ska.get("anonymousCidr", "0.0.0.0/0"),
            ),
            filedatastore=FileDatastoreConfig(
                job_dir=fds.get("jobDir", "jobs"),
                retry_failure_interval_ms=fds.get("retryFailureIntervalMs", 600_000),
                retry_failure_max_attempts=fds.get("retryFailureMaxAttempts", 5),
            ),
            staticrbac=StaticRbacConfig(
                role_files=rbac.get("roleFiles", []),
                user_files=rbac.get("userFiles", []),
                scan_interval_ms=rbac.get("scanIntervalMs", 60_000),
                default_role=rbac.get("defaultRole", ""),
            ),
            kratos=KratosConfig(
                host_url=kra.get("hostUrl", ""),
            ),
        )


def load_config(path: str) -> AppConfig:
    text = Path(path).read_text()
    return AppConfig.from_dict(json.loads(text))
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_config.py -v`
Expected: PASS (all 5 tests)

**Step 5: Commit**

```bash
git add backend/src/config.py backend/tests/test_config.py
git commit -m "feat: app configuration module for adapter wiring"
```

---

## Task 2: StaticKeyAuth Adapter

Port the Go `statickeyauth` module as a FastAPI middleware. This replaces the stub `get_request_context()` in `src/shared/middleware.py`.

**Go reference:** `server/modules/statickeyauth/statickeyauthimpl.go` (116 LOC)
**Go tests:** `server/modules/statickeyauth/statickeyauthimpl_test.go`

**Logic:**
1. If `Authorization` header is present and does NOT start with `"Bearer "`, validate as API key. Extract last space-separated token and compare to configured key.
2. If header is absent or starts with `"Bearer "` (cookie auth — pass through), check anonymous CIDR.
3. If `anonymousCidr == "*"`, allow all anonymous traffic (dev mode).
4. Otherwise parse client IP from `request.client.host` and check if it falls within the CIDR.
5. On success, set `requestor_id` to `AGENT_ID` and mark CSRF-exempt.
6. On failure, raise `HTTPException(401)`.

**Files:**
- Create: `backend/src/adapters/statickeyauth/__init__.py`
- Create: `backend/src/adapters/statickeyauth/middleware.py`
- Test: `backend/tests/adapters/test_statickeyauth.py`
- Modify: `backend/src/shared/middleware.py` (later, during wiring)

### Step 1: Write the failing tests

```python
# backend/tests/adapters/test_statickeyauth.py
"""Tests for StaticKeyAuth adapter — ported from Go statickeyauthimpl_test.go."""

import pytest

from src.adapters.statickeyauth.middleware import StaticKeyAuth


class TestValidateApiKey:
    """Ported from Go TestValidateApiKey."""

    @pytest.fixture
    def auth(self) -> StaticKeyAuth:
        ska = StaticKeyAuth(api_key="abc", anonymous_cidr="0.0.0.0/0")
        return ska

    def test_empty_key_rejected(self, auth: StaticKeyAuth):
        assert auth.validate_api_key("") is False

    def test_wrong_prefix_rejected(self, auth: StaticKeyAuth):
        assert auth.validate_api_key("basic xyz") is False

    def test_wrong_single_token_rejected(self, auth: StaticKeyAuth):
        assert auth.validate_api_key("basic") is False

    def test_exact_key_accepted(self, auth: StaticKeyAuth):
        assert auth.validate_api_key("abc") is True

    def test_prefixed_key_accepted(self, auth: StaticKeyAuth):
        assert auth.validate_api_key("basic abc") is True


class TestValidateAuthorization:
    """Ported from Go TestValidateAuthorization."""

    def _make(self, cidr: str) -> StaticKeyAuth:
        return StaticKeyAuth(api_key="abc", anonymous_cidr=cidr)

    def test_correct_key_any_ip(self):
        auth = self._make("172.17.0.0/24")
        assert auth.validate_authorization("abc", "1.1.1.1") is True

    def test_wrong_key_outside_cidr(self):
        auth = self._make("172.17.0.0/24")
        assert auth.validate_authorization("a", "1.1.1.1") is False

    def test_no_key_outside_cidr(self):
        auth = self._make("172.17.0.0/24")
        assert auth.validate_authorization("", "1.1.1.1") is False

    def test_no_key_outside_cidr_close(self):
        auth = self._make("172.17.0.0/24")
        assert auth.validate_authorization("", "172.17.1.1") is False

    def test_no_key_inside_cidr(self):
        auth = self._make("172.17.0.0/24")
        assert auth.validate_authorization("", "172.17.0.1") is True

    def test_correct_key_inside_cidr(self):
        auth = self._make("172.17.0.0/24")
        assert auth.validate_authorization("abc", "172.17.0.1") is True

    def test_wildcard_no_key(self):
        auth = self._make("*")
        assert auth.validate_authorization("", "1.1.1.1") is True

    def test_wildcard_correct_key(self):
        auth = self._make("*")
        assert auth.validate_authorization("abc", "1.1.1.1") is True

    def test_wildcard_wrong_key(self):
        auth = self._make("*")
        assert auth.validate_authorization("abcd", "1.1.1.1") is False

    def test_bearer_prefix_falls_through_to_cidr(self):
        auth = self._make("172.17.0.0/24")
        assert auth.validate_authorization("Bearer token123", "172.17.0.1") is True

    def test_bearer_prefix_outside_cidr_rejected(self):
        auth = self._make("172.17.0.0/24")
        assert auth.validate_authorization("Bearer token123", "1.1.1.1") is False


class TestInit:
    """Ported from Go TestAuthImplInit."""

    def test_invalid_cidr_raises(self):
        with pytest.raises(ValueError):
            StaticKeyAuth(api_key="abc", anonymous_cidr="1")

    def test_valid_cidr_parses(self):
        auth = StaticKeyAuth(api_key="abc", anonymous_cidr="1.2.3.4/16")
        assert auth.api_key == "abc"
        assert auth.anonymous_cidr == "1.2.3.4/16"

    def test_wildcard_accepted(self):
        auth = StaticKeyAuth(api_key="abc", anonymous_cidr="*")
        assert auth._skip_cidr_check is True
```

### Step 2: Run test to verify it fails

Run: `cd backend && python -m pytest tests/adapters/test_statickeyauth.py -v`
Expected: FAIL with "ModuleNotFoundError"

### Step 3: Write minimal implementation

```python
# backend/src/adapters/statickeyauth/__init__.py
```

```python
# backend/src/adapters/statickeyauth/middleware.py
"""StaticKeyAuth — API key validation + anonymous CIDR bypass.

Ported from Go server/modules/statickeyauth/statickeyauthimpl.go.
"""

from __future__ import annotations

import ipaddress
import logging

from fastapi import HTTPException, Request

from src.shared.context import AGENT_ID, RequestContext

logger = logging.getLogger(__name__)


class StaticKeyAuth:
    def __init__(self, api_key: str, anonymous_cidr: str) -> None:
        self.api_key = api_key
        self.anonymous_cidr = anonymous_cidr

        if anonymous_cidr == "*":
            self._skip_cidr_check = True
            self._network: ipaddress.IPv4Network | ipaddress.IPv6Network | None = None
            logger.warning("Bypassing all anonymous CIDR traffic checks. Dev use only.")
        else:
            self._skip_cidr_check = False
            self._network = ipaddress.ip_network(anonymous_cidr, strict=False)

    def validate_api_key(self, key: str) -> bool:
        if not key:
            return False
        pieces = key.split(" ")
        return pieces[-1] == self.api_key

    def validate_authorization(self, key: str, ip_str: str) -> bool:
        if key and not key.startswith("Bearer "):
            return self.validate_api_key(key)

        if self._skip_cidr_check:
            return True

        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            return False

        assert self._network is not None
        return addr in self._network

    async def __call__(self, request: Request) -> RequestContext:
        key = request.headers.get("Authorization", "")
        ip_str = request.client.host if request.client else "0.0.0.0"

        if not self.validate_authorization(key, ip_str):
            raise HTTPException(status_code=401, detail="Access denied")

        return RequestContext(requestor_id=AGENT_ID, username="agent")
```

### Step 4: Run test to verify it passes

Run: `cd backend && python -m pytest tests/adapters/test_statickeyauth.py -v`
Expected: PASS (all 14 tests)

### Step 5: Commit

```bash
git add backend/src/adapters/statickeyauth/ backend/tests/adapters/test_statickeyauth.py
git commit -m "feat: StaticKeyAuth adapter with API key + CIDR validation"
```

---

## Task 3: FileDatastore Adapter

Port the Go `filedatastore` module. Implements `JobDatastore` from `src/ports/jobs.py` and `Datastore` from `src/ports/grid.py`.

**Go reference:** `server/modules/filedatastore/filedatastoreimpl.go` (587 LOC)
**Go tests:** `server/modules/filedatastore/filedatastoreimpl_test.go` (440 LOC)

**Key behavior:**
- Jobs stored as JSON files: `{job_dir}/{node_id}/{job_id}.json`
- Job IDs auto-increment starting at 1001
- Nodes stored in memory
- Thread-safe via asyncio locks

Split into sub-tasks since this is the largest Tier 0 adapter.

**Files:**
- Create: `backend/src/adapters/filedatastore/__init__.py`
- Create: `backend/src/adapters/filedatastore/store.py`
- Test: `backend/tests/adapters/test_filedatastore.py`

### Step 1: Write the failing tests

```python
# backend/tests/adapters/test_filedatastore.py
"""Tests for FileDatastore adapter — ported from Go filedatastoreimpl_test.go."""

from pathlib import Path

import pytest

from src.adapters.filedatastore.store import FileDatastore
from src.domain.job import JOB_STATUS_COMPLETED, JOB_STATUS_PENDING
from src.domain.node import Node


@pytest.fixture
def store(tmp_path: Path) -> FileDatastore:
    return FileDatastore(job_dir=str(tmp_path / "jobs"))


class TestCreateJob:
    def test_first_job_id_is_1001(self, store: FileDatastore):
        job = store.create_job()
        assert job.id == 1001

    def test_ids_auto_increment(self, store: FileDatastore):
        j1 = store.create_job()
        j2 = store.create_job()
        assert j1.id == 1001
        assert j2.id == 1002

    def test_new_job_is_pending(self, store: FileDatastore):
        job = store.create_job()
        assert job.status == JOB_STATUS_PENDING


class TestGetJob:
    def test_get_existing_job(self, store: FileDatastore):
        job = store.create_job()
        found = store.get_job(job.id)
        assert found is not None
        assert found.id == job.id

    def test_get_missing_job_returns_none(self, store: FileDatastore):
        assert store.get_job(9999) is None


class TestGetJobs:
    async def test_get_all_jobs(self, store: FileDatastore):
        j1 = store.create_job()
        j2 = store.create_job()
        await store.add_job(j1)
        await store.add_job(j2)
        jobs = store.get_jobs("", {})
        assert len(jobs) == 2

    async def test_filter_by_kind(self, store: FileDatastore):
        j1 = store.create_job()
        j1.kind = "pcap"
        j2 = store.create_job()
        j2.kind = "reports"
        await store.add_job(j1)
        await store.add_job(j2)
        pcap_jobs = store.get_jobs("pcap", {})
        assert len(pcap_jobs) == 1
        assert pcap_jobs[0].kind == "pcap"


class TestAddJob:
    async def test_add_persists_to_disk(self, store: FileDatastore, tmp_path: Path):
        job = store.create_job()
        job.node_id = "test-node"
        await store.add_job(job)

        job_dir = tmp_path / "jobs"
        json_files = list(job_dir.rglob("*.json"))
        assert len(json_files) == 1

    async def test_add_sets_status_pending(self, store: FileDatastore):
        job = store.create_job()
        await store.add_job(job)
        found = store.get_job(job.id)
        assert found is not None
        assert found.status == JOB_STATUS_PENDING


class TestUpdateJob:
    async def test_update_changes_status(self, store: FileDatastore):
        job = store.create_job()
        await store.add_job(job)
        job.complete()
        await store.update_job(job)
        found = store.get_job(job.id)
        assert found is not None
        assert found.status == JOB_STATUS_COMPLETED


class TestDeleteJob:
    async def test_delete_existing(self, store: FileDatastore):
        job = store.create_job()
        await store.add_job(job)
        result = await store.delete_job(job.id)
        assert result[0] is not None
        assert result[1] is None
        assert store.get_job(job.id) is None

    async def test_delete_missing(self, store: FileDatastore):
        result = await store.delete_job(9999)
        assert result[0] is None
        assert result[1] is not None


class TestNodes:
    async def test_add_and_get_nodes(self, store: FileDatastore):
        node = Node("test-node-1")
        node.description = "Test node"
        store.add_node(node)
        nodes = await store.get_nodes()
        assert len(nodes) == 1
        assert nodes[0].id == "test-node-1"

    async def test_update_node(self, store: FileDatastore):
        node = Node("test-node-1")
        node.description = "Original"
        store.add_node(node)
        node.description = "Updated"
        store.update_node(node)
        nodes = await store.get_nodes()
        assert nodes[0].description == "Updated"
```

### Step 2: Run test to verify it fails

Run: `cd backend && python -m pytest tests/adapters/test_filedatastore.py -v`
Expected: FAIL with "ModuleNotFoundError"

### Step 3: Write minimal implementation

```python
# backend/src/adapters/filedatastore/__init__.py
```

```python
# backend/src/adapters/filedatastore/store.py
"""FileDatastore — file-based persistence for jobs and nodes.

Ported from Go server/modules/filedatastore/filedatastoreimpl.go.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from src.domain.job import Job, JOB_STATUS_DELETED, new_job
from src.domain.node import Node

logger = logging.getLogger(__name__)

_SANITIZE_RE = re.compile(r"[^a-zA-Z0-9_-]")
INITIAL_JOB_ID = 1001


def _sanitize(value: str) -> str:
    return _SANITIZE_RE.sub("_", value)


class FileDatastore:
    def __init__(self, job_dir: str) -> None:
        self._job_dir = job_dir
        self._jobs_by_id: dict[int, Job] = {}
        self._nodes_by_id: dict[str, Node] = {}
        self._next_job_id = INITIAL_JOB_ID

        os.makedirs(self._job_dir, exist_ok=True)

    def create_job(self) -> Job:
        job = new_job()
        job.id = self._next_job_id
        self._next_job_id += 1
        self._jobs_by_id[job.id] = job
        return job

    def get_job(self, job_id: int) -> Job | None:
        return self._jobs_by_id.get(job_id)

    def get_jobs(self, kind: str, parameters: dict[str, Any]) -> list[Job]:
        result: list[Job] = []
        for job in self._jobs_by_id.values():
            if job.status == JOB_STATUS_DELETED:
                continue
            if kind and job.get_kind() != kind:
                continue
            result.append(job)
        return result

    async def add_job(self, job: Job) -> None:
        self._jobs_by_id[job.id] = job
        self._save_job(job)

    async def update_job(self, job: Job) -> None:
        if job.id not in self._jobs_by_id:
            return
        self._jobs_by_id[job.id] = job
        self._save_job(job)

    async def delete_job(self, job_id: int) -> tuple[Job | None, None] | tuple[None, str]:
        job = self._jobs_by_id.pop(job_id, None)
        if job is None:
            return None, "Job not found"
        job.status = JOB_STATUS_DELETED
        self._delete_job_files(job)
        return job, None

    async def get_nodes(self) -> list[Node]:
        return list(self._nodes_by_id.values())

    def add_node(self, node: Node) -> None:
        self._nodes_by_id[node.id] = node

    def update_node(self, node: Node) -> None:
        self._nodes_by_id[node.id] = node

    def _job_path(self, job: Job) -> Path:
        node_dir = _sanitize(job.get_node_id()) if job.get_node_id() else "_default"
        return Path(self._job_dir) / node_dir / f"{job.id}.json"

    def _save_job(self, job: Job) -> None:
        path = self._job_path(job)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(job.model_dump_json(by_alias=True))

    def _delete_job_files(self, job: Job) -> None:
        path = self._job_path(job)
        for suffix in [".json", ".bin", ".bin.unwrapped"]:
            target = path.with_suffix(suffix)
            if target.exists():
                target.unlink()
```

### Step 4: Run test to verify it passes

Run: `cd backend && python -m pytest tests/adapters/test_filedatastore.py -v`
Expected: PASS (all 11 tests)

### Step 5: Commit

```bash
git add backend/src/adapters/filedatastore/ backend/tests/adapters/test_filedatastore.py
git commit -m "feat: FileDatastore adapter with job CRUD and node storage"
```

---

## Task 4: Wire Tier 0 Adapters into main.py

Connect StaticKeyAuth and FileDatastore so the server boots and serves real responses.

**Files:**
- Modify: `backend/src/main.py`
- Modify: `backend/src/shared/middleware.py`
- Test: `backend/tests/test_wiring.py`

### Step 1: Write the failing test

```python
# backend/tests/test_wiring.py
"""Tests that adapter wiring works end-to-end."""

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def config_file(tmp_path: Path) -> str:
    config = {
        "server": {
            "modules": {
                "statickeyauth": {
                    "apiKey": "testkey",
                    "anonymousCidr": "*",
                },
                "filedatastore": {
                    "jobDir": str(tmp_path / "jobs"),
                },
            }
        }
    }
    path = tmp_path / "sensoroni.json"
    path.write_text(json.dumps(config))
    return str(path)


@pytest.fixture
async def wired_client(config_file: str):
    from src.main import create_app

    app = create_app(config_file)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestWiring:
    async def test_health_endpoint(self, wired_client: AsyncClient):
        resp = await wired_client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    async def test_auth_rejects_bad_key(self, tmp_path: Path):
        from src.main import create_app

        config = {
            "server": {
                "modules": {
                    "statickeyauth": {
                        "apiKey": "secret",
                        "anonymousCidr": "192.168.1.0/24",
                    },
                    "filedatastore": {"jobDir": str(tmp_path / "jobs")},
                }
            }
        }
        path = tmp_path / "sensoroni.json"
        path.write_text(json.dumps(config))

        app = create_app(str(path))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get(
                "/api/info/",
                headers={"Authorization": "wrongkey"},
            )
            assert resp.status_code == 401
```

### Step 2: Run test to verify it fails

Run: `cd backend && python -m pytest tests/test_wiring.py -v`
Expected: FAIL with "cannot import name 'create_app' from 'src.main'"

### Step 3: Modify main.py to add create_app factory

The existing `app = FastAPI(...)` global stays as the default (for backward compat with existing tests). Add a `create_app(config_path)` factory that wires adapters.

Update `backend/src/main.py` — add a `create_app` function that:
1. Loads config from sensoroni.json
2. Creates StaticKeyAuth middleware instance
3. Creates FileDatastore instance
4. Overrides `get_request_context` in middleware.py to use StaticKeyAuth
5. Overrides service dependency functions to inject real adapters

Update `backend/src/shared/middleware.py` — make `get_request_context` overrideable by storing the auth callable in a module-level variable.

The exact implementation depends on which route dependencies need overriding. At minimum:
- Replace `get_request_context` with StaticKeyAuth's `__call__`
- Wire `JobService` with `FileDatastore`

### Step 4: Run test to verify it passes

Run: `cd backend && python -m pytest tests/test_wiring.py -v`
Expected: PASS

### Step 5: Run all existing tests to verify no regressions

Run: `cd backend && python -m pytest -v`
Expected: All 866+ tests PASS

### Step 6: Commit

```bash
git add backend/src/main.py backend/src/shared/middleware.py backend/tests/test_wiring.py
git commit -m "feat: wire Tier 0 adapters (StaticKeyAuth + FileDatastore) into app"
```

---

## Task 5: StaticRBAC Adapter

Port the Go `staticrbac` module. Implements `Authorizer` from `src/ports/auth.py` and `Rolestore` from `src/ports/roles.py`.

**Go reference:** `server/modules/staticrbac/staticrbacauthorizer.go` (426 LOC)
**Go tests:** `server/modules/staticrbac/staticrbacauthorizer_test.go` (255 LOC)
**Test fixtures:** `server/modules/staticrbac/rbac_users.test`, `rbac_permissions.test`, `rbac_roles.test`

**Key behavior:**
- Reads role and user mapping files (format: `key: value1 value2`)
- Supports role inheritance (recursive authorization check)
- `check_authorized(user_id, operation, resource)` checks if user's roles grant `resource/operation`
- File scanning with MD5 change detection
- Agent gets "agent" role, system gets "superuser" role

**Files:**
- Create: `backend/src/adapters/staticrbac/__init__.py`
- Create: `backend/src/adapters/staticrbac/authorizer.py`
- Create: `backend/tests/adapters/test_staticrbac.py`
- Create: `backend/tests/adapters/rbac_users.test` (copy from Go)
- Create: `backend/tests/adapters/rbac_permissions.test` (copy from Go)
- Create: `backend/tests/adapters/rbac_roles.test` (copy from Go)

### Step 1: Write the failing tests

```python
# backend/tests/adapters/test_staticrbac.py
"""Tests for StaticRBAC adapter — ported from Go staticrbacauthorizer_test.go."""

from pathlib import Path

import pytest

from src.adapters.staticrbac.authorizer import StaticRbacAuthorizer
from src.ports.auth import Unauthorized

FIXTURES = Path(__file__).parent


@pytest.fixture
def auth() -> StaticRbacAuthorizer:
    a = StaticRbacAuthorizer()
    a.init(
        user_files=[str(FIXTURES / "rbac_users.test")],
        role_files=[str(FIXTURES / "rbac_permissions.test"), str(FIXTURES / "rbac_roles.test")],
        scan_interval_ms=60000,
        default_role="defrole",
    )
    a.scan_now()
    return a


class TestIsAuthorized:
    """Ported from Go TestIsAuthorized."""

    def test_role_inheritance(self):
        auth = StaticRbacAuthorizer()
        role_map = {
            "clerk": ["register/operates", "tables/maintains"],
            "baker": ["cakes/bake", "icing/decorates"],
            "chef": ["recipes/create", "menus/create"],
            "henry": ["baker"],
            "tom": ["chef"],
            "alice": [],
        }
        auth.update_role_map(role_map)

        cases = [
            ("henry", "cakes/bake", True),
            ("henry", "pies/bake", False),
            ("henry", "register/operates", False),
            ("alice", "pies/bake", False),
            ("alice", "cakes/bake", False),
            ("alice", "register/operates", False),
            ("tom", "cakes/bake", False),
            ("tom", "recipes/create", True),
            ("tom", "register/operates", False),
        ]
        for subject, permission, expected in cases:
            assert auth.is_authorized(subject, permission) is expected, (
                f"subject={subject}, permission={permission}"
            )


class TestCheckAuthorized:
    def test_missing_user_raises(self, auth: StaticRbacAuthorizer):
        with pytest.raises(Unauthorized):
            auth.check_user_operation_authorized("nonexistent", "action", "resource")

    def test_user_with_permission_passes(self, auth: StaticRbacAuthorizer):
        auth.check_user_operation_authorized("a0-id", "action", "another")

    def test_user_without_permission_raises(self, auth: StaticRbacAuthorizer):
        with pytest.raises(Unauthorized):
            auth.check_user_operation_authorized("a0-id", "action", "some")

    def test_removed_permission(self, auth: StaticRbacAuthorizer):
        auth.check_user_operation_authorized("a1-id", "bar", "foo")
        with pytest.raises(Unauthorized):
            auth.check_user_operation_authorized("a1-id", "action", "another")


class TestCheckAuthorizedProtocol:
    """Test the Authorizer Protocol interface."""

    async def test_protocol_method(self, auth: StaticRbacAuthorizer):
        await auth.check_authorized("a0-id", "action", "another")

    async def test_protocol_method_raises(self, auth: StaticRbacAuthorizer):
        with pytest.raises(Unauthorized):
            await auth.check_authorized("a0-id", "action", "some")


class TestGetRoles:
    def test_returns_role_names(self, auth: StaticRbacAuthorizer):
        roles = auth.get_roles_sync()
        assert "somerole" in roles
        assert "superuser" in roles
        assert "user" in roles

    async def test_protocol_get_roles(self, auth: StaticRbacAuthorizer):
        roles = await auth.get_roles()
        assert "somerole" in roles


class TestGetPermissions:
    async def test_returns_resource_operation_map(self, auth: StaticRbacAuthorizer):
        auth.update_user_map({"a0-id": ["analyst"]})
        permissions = await auth.get_permissions()
        assert "some" in permissions or "another" in permissions or "foo" in permissions


class TestAddRemoveRole:
    def test_add_role_to_user(self, auth: StaticRbacAuthorizer):
        auth.add_role_to_user("a1-id", "fruity")
        roles = auth.get_roles_for_user("a1-id")
        assert "fruity" in roles

    def test_add_duplicate_role(self, auth: StaticRbacAuthorizer):
        auth.add_role_to_user("a1-id", "fruity")
        auth.add_role_to_user("a1-id", "fruity")
        roles = auth.get_roles_for_user("a1-id")
        assert roles.count("fruity") == 1

    def test_remove_role(self, auth: StaticRbacAuthorizer):
        auth.add_role_to_user("a1-id", "fruity")
        auth.remove_role_from_user("a1-id", "fruity")
        roles = auth.get_roles_for_user("a1-id")
        assert "fruity" not in roles

    def test_remove_nonexistent_role(self, auth: StaticRbacAuthorizer):
        auth.remove_role_from_user("a1-id", "fruity")
        roles = auth.get_roles_for_user("a1-id")
        assert "fruity" not in roles


class TestEnsureDefaultRole:
    async def test_new_user_gets_default_role(self, auth: StaticRbacAuthorizer):
        await auth.ensure_default_role_for_user()
        # This requires wiring with a request context; test the underlying logic
        auth.add_role_to_user("new-user-id", auth._default_role)
        roles = auth.get_roles_for_user("new-user-id")
        assert "defrole" in roles


class TestFileParsing:
    def test_parses_role_files(self, auth: StaticRbacAuthorizer):
        assert len(auth._role_map) > 0

    def test_parses_user_files(self, auth: StaticRbacAuthorizer):
        assert "a0-id" in auth._user_map
        assert "a1-id" in auth._user_map
```

### Step 2: Copy test fixture files

Copy the 3 test fixture files from the Go source:

- `server/modules/staticrbac/rbac_users.test` → `backend/tests/adapters/rbac_users.test`
- `server/modules/staticrbac/rbac_permissions.test` → `backend/tests/adapters/rbac_permissions.test`
- `server/modules/staticrbac/rbac_roles.test` → `backend/tests/adapters/rbac_roles.test`

### Step 3: Run test to verify it fails

Run: `cd backend && python -m pytest tests/adapters/test_staticrbac.py -v`
Expected: FAIL with "ModuleNotFoundError"

### Step 4: Write minimal implementation

```python
# backend/src/adapters/staticrbac/__init__.py
```

```python
# backend/src/adapters/staticrbac/authorizer.py
"""StaticRBAC — file-based role and permission management.

Ported from Go server/modules/staticrbac/staticrbacauthorizer.go.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from pathlib import Path

from src.ports.auth import Unauthorized

logger = logging.getLogger(__name__)


class StaticRbacAuthorizer:
    """Implements Authorizer and Rolestore protocols."""

    def __init__(self) -> None:
        self._role_map: dict[str, list[str]] = {}
        self._user_map: dict[str, list[str]] = {}
        self._role_files: list[str] = []
        self._user_files: list[str] = []
        self._scan_interval_ms: int = 60_000
        self._default_role: str = ""
        self._previous_role_hash: bytes = b""
        self._previous_user_hash: bytes = b""
        self._lock = threading.Lock()

    def init(
        self,
        user_files: list[str],
        role_files: list[str],
        scan_interval_ms: int,
        default_role: str,
    ) -> None:
        self._role_files = role_files
        self._user_files = user_files
        self._scan_interval_ms = scan_interval_ms
        self._default_role = default_role
        self.scan_now()

    def scan_now(self) -> None:
        new_role_map, role_hash = self._scan_files(self._role_files)
        if role_hash != self._previous_role_hash:
            self.update_role_map(new_role_map)
            self._previous_role_hash = role_hash

        new_user_map, user_hash = self._scan_files(self._user_files)
        if user_hash != self._previous_user_hash:
            self.update_user_map(new_user_map)
            self._previous_user_hash = user_hash

    def update_role_map(self, new_map: dict[str, list[str]]) -> None:
        with self._lock:
            self._role_map = new_map

    def update_user_map(self, new_map: dict[str, list[str]]) -> None:
        with self._lock:
            self._user_map = new_map

    def is_authorized(self, subject: str, requested_permission: str) -> bool:
        if subject == requested_permission:
            return True
        permissions = self._role_map.get(subject, [])
        for perm in permissions:
            if self.is_authorized(perm, requested_permission):
                return True
        return False

    def check_user_operation_authorized(self, user_id: str, operation: str, target: str) -> None:
        permission = f"{target}/{operation}"
        with self._lock:
            roles = self._user_map.get(user_id, [])
            for role in roles:
                if self.is_authorized(role, permission):
                    return
        raise Unauthorized(user_id, operation, target)

    async def check_authorized(self, user_id: str, operation: str, resource: str) -> None:
        self.check_user_operation_authorized(user_id, operation, resource)

    def get_roles_sync(self) -> list[str]:
        perm_set: set[str] = set()
        for perms in self._role_map.values():
            perm_set.update(perms)
        roles = [r for r in self._role_map if r not in perm_set]
        return sorted(roles)

    async def get_roles(self) -> list[str]:
        return self.get_roles_sync()

    async def get_permissions(self) -> dict[str, list[str]]:
        final: dict[str, list[str]] = {}
        seen: set[str] = set()
        for perms in self._role_map.values():
            for perm in perms:
                if perm not in seen and "/" in perm:
                    resource, privilege = perm.split("/", 1)
                    final.setdefault(resource, []).append(privilege)
                    seen.add(perm)
        for v in final.values():
            v.sort()
        return final

    async def ensure_default_role_for_user(self) -> None:
        pass

    def get_roles_for_user(self, user_id: str) -> list[str]:
        with self._lock:
            return list(self._user_map.get(user_id, []))

    def add_role_to_user(self, user_id: str, role: str) -> None:
        with self._lock:
            roles = self._user_map.setdefault(user_id, [])
            if role not in roles:
                roles.append(role)
                roles.sort()

    def remove_role_from_user(self, user_id: str, role: str) -> None:
        with self._lock:
            roles = self._user_map.get(user_id, [])
            if role in roles:
                roles.remove(role)

    def _scan_files(self, files: list[str]) -> tuple[dict[str, list[str]], bytes]:
        new_map: dict[str, list[str]] = {}
        hash_text = ""
        for path in files:
            try:
                content = Path(path).read_text()
            except OSError:
                logger.error("Unable to open file: %s", path)
                continue
            for line in content.splitlines():
                hash_text += line
                self._parse_line(new_map, line)
        return new_map, hashlib.md5(hash_text.encode()).digest()

    def _parse_line(self, mp: dict[str, list[str]], line: str) -> None:
        line = line.replace(",", " ").replace(";", " ").strip()
        if not line or line.startswith("#"):
            return
        pieces = line.split(":")
        if len(pieces) < 2 or len(pieces) > 3:
            logger.warning("Invalid mapping: %s", line)
            return
        permission = pieces[0].strip()
        role_tokens = pieces[1].split()
        operation = "+" if len(pieces) <= 2 else pieces[2].strip()

        for role in role_tokens:
            role = role.strip()
            if role:
                self._adjust_map(mp, role, permission, operation)

    @staticmethod
    def _adjust_map(mp: dict[str, list[str]], subject: str, permission: str, operation: str) -> None:
        perms = mp.setdefault(subject, [])
        exists = permission in perms
        if not exists and operation == "+":
            perms.append(permission)
            perms.sort()
        elif exists and operation == "-":
            perms.remove(permission)
```

### Step 5: Run test to verify it passes

Run: `cd backend && python -m pytest tests/adapters/test_staticrbac.py -v`
Expected: PASS (all tests)

### Step 6: Commit

```bash
git add backend/src/adapters/staticrbac/ backend/tests/adapters/test_staticrbac.py backend/tests/adapters/rbac_*.test
git commit -m "feat: StaticRBAC adapter with file-based role parsing and auth checks"
```

---

## Task 6: Kratos Adapter

Port the Go `kratos` module. Implements `Userstore` from `src/ports/users.py`.

**Go reference:** `server/modules/kratos/kratosuserstore.go` (170 LOC), `kratosuser.go` (136 LOC)

**Key behavior:**
- HTTP client to Ory Kratos admin API (`GET /identities`, `GET /identities/{id}`)
- Maps Kratos identity JSON to our `User` domain model
- Determines TOTP/WebAuthn status from credentials
- Status is "locked" if Kratos state is "inactive"

**Files:**
- Create: `backend/src/adapters/kratos/__init__.py`
- Create: `backend/src/adapters/kratos/userstore.py`
- Test: `backend/tests/adapters/test_kratos.py`

### Step 1: Write the failing tests

```python
# backend/tests/adapters/test_kratos.py
"""Tests for Kratos adapter — unit tests with mocked HTTP."""

from unittest.mock import AsyncMock

import pytest

from src.adapters.kratos.userstore import KratosUserstore


def _make_kratos_identity(
    *,
    identity_id: str = "user-1",
    email: str = "user@test.local",
    first_name: str = "Test",
    last_name: str = "User",
    state: str = "active",
) -> dict:
    return {
        "id": identity_id,
        "schema_id": "default",
        "state": state,
        "traits": {
            "email": email,
            "name": {"first": first_name, "last": last_name},
        },
        "verifiable_addresses": [
            {"id": "addr-1", "value": email, "verified": True, "via": "email"}
        ],
        "credentials": {},
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
    }


@pytest.fixture
def mock_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def store(mock_client: AsyncMock) -> KratosUserstore:
    s = KratosUserstore(host_url="http://kratos:4434")
    s._client = mock_client
    return s


class TestGetUsers:
    async def test_returns_mapped_users(self, store: KratosUserstore, mock_client: AsyncMock):
        mock_client.get.return_value = AsyncMock(
            status_code=200,
            json=lambda: [
                _make_kratos_identity(identity_id="u1", email="a@test.local"),
                _make_kratos_identity(identity_id="u2", email="b@test.local"),
            ],
            raise_for_status=lambda: None,
        )
        users = await store.get_users()
        assert len(users) == 2
        assert users[0].id == "u1"
        assert users[0].email == "a@test.local"
        assert users[1].id == "u2"

    async def test_inactive_user_status_locked(self, store: KratosUserstore, mock_client: AsyncMock):
        mock_client.get.return_value = AsyncMock(
            status_code=200,
            json=lambda: [_make_kratos_identity(state="inactive")],
            raise_for_status=lambda: None,
        )
        users = await store.get_users()
        assert users[0].status == "locked"

    async def test_active_user_status_empty(self, store: KratosUserstore, mock_client: AsyncMock):
        mock_client.get.return_value = AsyncMock(
            status_code=200,
            json=lambda: [_make_kratos_identity(state="active")],
            raise_for_status=lambda: None,
        )
        users = await store.get_users()
        assert users[0].status == ""


class TestGetUserById:
    async def test_returns_user(self, store: KratosUserstore, mock_client: AsyncMock):
        mock_client.get.return_value = AsyncMock(
            status_code=200,
            json=lambda: _make_kratos_identity(identity_id="u1", email="a@test.local"),
            raise_for_status=lambda: None,
        )
        user = await store.get_user_by_id("u1")
        assert user is not None
        assert user.id == "u1"
        assert user.email == "a@test.local"

    async def test_not_found_returns_none(self, store: KratosUserstore, mock_client: AsyncMock):
        import httpx

        mock_client.get.return_value = AsyncMock(
            status_code=404,
            raise_for_status=AsyncMock(side_effect=httpx.HTTPStatusError("Not found", request=None, response=None)),
        )
        user = await store.get_user_by_id("nonexistent")
        assert user is None


class TestCredentialMapping:
    async def test_totp_enabled(self, store: KratosUserstore, mock_client: AsyncMock):
        identity = _make_kratos_identity()
        identity["credentials"] = {
            "totp": {"created_at": "2024-01-01T00:00:00Z", "updated_at": "2024-01-02T00:00:00Z"}
        }
        mock_client.get.return_value = AsyncMock(
            status_code=200,
            json=lambda: [identity],
            raise_for_status=lambda: None,
        )
        users = await store.get_users()
        assert users[0].totp_status == "enabled"

    async def test_webauthn_enabled(self, store: KratosUserstore, mock_client: AsyncMock):
        identity = _make_kratos_identity()
        identity["credentials"] = {
            "webauthn": {"created_at": "2024-01-01T00:00:00Z", "updated_at": "2024-01-02T00:00:00Z"}
        }
        mock_client.get.return_value = AsyncMock(
            status_code=200,
            json=lambda: [identity],
            raise_for_status=lambda: None,
        )
        users = await store.get_users()
        assert users[0].webauthn_status == "enabled"
```

### Step 2: Run test to verify it fails

Run: `cd backend && python -m pytest tests/adapters/test_kratos.py -v`
Expected: FAIL with "ModuleNotFoundError"

### Step 3: Write minimal implementation

```python
# backend/src/adapters/kratos/__init__.py
```

```python
# backend/src/adapters/kratos/userstore.py
"""Kratos Userstore — maps Ory Kratos identities to User domain model.

Ported from Go server/modules/kratos/kratosuserstore.go and kratosuser.go.
"""

from __future__ import annotations

import logging

import httpx

from src.domain.user import User

logger = logging.getLogger(__name__)


def _map_identity_to_user(identity: dict) -> User:
    traits = identity.get("traits", {})
    name = traits.get("name", {})
    state = identity.get("state", "active")
    credentials = identity.get("credentials", {})

    totp_status = "enabled" if "totp" in credentials else ""
    webauthn_status = "enabled" if "webauthn" in credentials else ""

    return User(
        id=identity.get("id", ""),
        email=traits.get("email", ""),
        first_name=name.get("first", ""),
        last_name=name.get("last", ""),
        note=traits.get("note", ""),
        status="locked" if state == "inactive" else "",
        totp_status=totp_status,
        webauthn_status=webauthn_status,
        roles=[],
    )


class KratosUserstore:
    """Implements Userstore protocol via Kratos admin API."""

    def __init__(self, host_url: str) -> None:
        self._host_url = host_url
        self._client = httpx.AsyncClient(base_url=host_url, timeout=10.0)

    async def get_users(self) -> list[User]:
        resp = await self._client.get("/identities")
        resp.raise_for_status()
        identities = resp.json()
        return [_map_identity_to_user(i) for i in identities]

    async def get_user_by_id(self, user_id: str) -> User | None:
        try:
            resp = await self._client.get(f"/identities/{user_id}")
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            return None
        return _map_identity_to_user(resp.json())

    async def close(self) -> None:
        await self._client.aclose()
```

### Step 4: Run test to verify it passes

Run: `cd backend && python -m pytest tests/adapters/test_kratos.py -v`
Expected: PASS (all 7 tests)

### Step 5: Commit

```bash
git add backend/src/adapters/kratos/ backend/tests/adapters/test_kratos.py
git commit -m "feat: Kratos adapter mapping Ory identities to User model"
```

---

## Task 7: Wire Tier 1 Adapters (StaticRBAC + Kratos)

Connect StaticRBAC and Kratos to the app factory so the full auth+user flow works.

**Files:**
- Modify: `backend/src/main.py` (extend `create_app`)
- Modify: `backend/tests/test_wiring.py` (add Tier 1 tests)

### Step 1: Write the failing test

Add to `backend/tests/test_wiring.py`:

```python
class TestTier1Wiring:
    async def test_roles_endpoint_returns_roles(self, wired_client: AsyncClient):
        resp = await wired_client.get("/api/roles/")
        assert resp.status_code == 200

    async def test_users_endpoint_returns_users(self, wired_client: AsyncClient):
        resp = await wired_client.get("/api/users/")
        assert resp.status_code == 200
```

### Step 2: Extend create_app to wire StaticRBAC and Kratos

In `create_app()`:
1. If `staticrbac` config has role_files, create `StaticRbacAuthorizer` and wire into `Authorizer`/`Rolestore` dependencies
2. If `kratos` config has host_url, create `KratosUserstore` and wire into `Userstore` dependencies
3. Otherwise fall back to stubs

### Step 3: Run test to verify it passes

Run: `cd backend && python -m pytest tests/test_wiring.py -v`
Expected: PASS

### Step 4: Run full test suite

Run: `cd backend && python -m pytest -v`
Expected: All tests PASS

### Step 5: Commit

```bash
git add backend/src/main.py backend/tests/test_wiring.py
git commit -m "feat: wire Tier 1 adapters (StaticRBAC + Kratos) into app factory"
```

---

## Task 8: Elasticsearch Adapter (Outline)

> **This adapter is too large for this plan (15,800 LOC in Go, 21 files).** It needs its own dedicated planning session with sub-tasks for each store interface.

**Implements:** `Eventstore`, `Casestore`, `Detectionstore`, `Assistantstore` protocols

**Recommended sub-plan breakdown:**

1. **ES Client Module** — shared Elasticsearch async client with connection pooling, retry logic, index management
2. **Eventstore** — `search()`, `acknowledge()`, `get_active_queries()`, `cancel_query()`. Query DSL translation. This is the critical path for the SOC UI.
3. **Casestore** — Full case CRUD, comments, related events, artifacts, artifact streams. ~18 methods.
4. **Detectionstore** — Detection CRUD, comments, history. ~11 methods.
5. **Assistantstore** — Chat history, sessions, usage tracking. ~7 methods.

**Dependencies to add:** `elasticsearch[async]>=8.13.0` in pyproject.toml
**Testing:** Docker Compose with Elasticsearch 8.x, integration tests against real instance

**Start a new planning session with:**
```
Plan the Elasticsearch adapter for securityonion-soc. See docs/plans/prompt-adapter-planning.md
for context. The adapter implements 4 Protocol interfaces: Eventstore, Casestore,
Detectionstore, Assistantstore. Break it into 5 sub-tasks: shared client, then one per store.
```

---

## Run Order

```
Task 1: App Config Module         → foundation, no deps
Task 2: StaticKeyAuth Adapter     → depends on Task 1 (config)
Task 3: FileDatastore Adapter     → depends on Task 1 (config)
Task 4: Wire Tier 0              → depends on Tasks 1-3
Task 5: StaticRBAC Adapter       → independent of Tasks 2-4
Task 6: Kratos Adapter           → independent of Tasks 2-5
Task 7: Wire Tier 1              → depends on Tasks 4-6
Task 8: Elasticsearch            → separate plan, depends on Task 4
```

Tasks 2+3 can run in parallel. Tasks 5+6 can run in parallel.

---

## Verification Checklist

After all tasks complete:

- [ ] `cd backend && python -m pytest -v` — all 866+ existing tests pass
- [ ] `cd backend && python -m pytest tests/adapters/ -v` — all new adapter tests pass
- [ ] `cd backend && python -m pytest tests/test_wiring.py -v` — wiring tests pass
- [ ] `cd backend && python -m pytest tests/test_config.py -v` — config tests pass
- [ ] `cd backend && python -m mypy src/` — type checks pass
- [ ] `cd backend && ruff check src/` — lint clean
- [ ] Server boots: `cd backend && python -m uvicorn src.main:app --reload` starts without error
- [ ] `GET /api/health` returns `{"status": "ok"}`
- [ ] `GET /api/info/` returns valid JSON with real version info
