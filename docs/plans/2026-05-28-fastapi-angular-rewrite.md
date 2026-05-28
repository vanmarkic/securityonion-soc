# SecurityOnion SOC Rewrite — FastAPI + Angular

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rewrite securityonion-soc from Go+Vue to FastAPI+Angular with hexagonal+services architecture, preserving all API behavior.

**Architecture:** Hexagonal + Services. `domain/` (pure Python entities), `ports/` (Protocol interfaces), `services/` (business logic), `api/` (FastAPI routers), `adapters/` (integration stubs for now), `shared/` (middleware, auth, errors). Frontend: Angular with feature modules, Signals for state, facade pattern per feature.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic v2, uvicorn, pytest, httpx, Schemathesis. Angular 19+, TypeScript 5.x, Angular Material, RxJS, Angular Signals.

**Branch:** `rewrite/v4` (same repo, Go code at `server/`, `model/`, `html/` for reference)

**Source reference:** All Go code lives in the same repo. When the plan says "reference `server/detectionhandler.go`", look at the Go file in this repo.

---

## Phase 0: Project Scaffolding + Characterization Tests

### Task 0.1: Python Project Skeleton

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/src/__init__.py`
- Create: `backend/src/main.py`
- Create: `backend/src/domain/__init__.py`
- Create: `backend/src/ports/__init__.py`
- Create: `backend/src/services/__init__.py`
- Create: `backend/src/api/__init__.py`
- Create: `backend/src/adapters/__init__.py`
- Create: `backend/src/shared/__init__.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`

**Step 1: Create pyproject.toml**

```toml
[project]
name = "securityonion-soc"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "pydantic>=2.10.0",
    "httpx>=0.28.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24.0",
    "httpx>=0.28.0",
    "ruff>=0.8.0",
    "mypy>=1.13.0",
    "schemathesis>=3.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
target-version = "py312"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.mypy]
python_version = "3.12"
strict = true
```

**Step 2: Create main.py with health check**

```python
# backend/src/main.py
from fastapi import FastAPI

app = FastAPI(title="SecurityOnion SOC", version="0.1.0")

@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

**Step 3: Create conftest.py with test client**

```python
# backend/tests/conftest.py
import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app

@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
```

**Step 4: Write the first test**

```python
# backend/tests/test_health.py
import pytest

async def test_health(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

**Step 5: Run test**

Run: `cd backend && pip install -e ".[dev]" && pytest tests/test_health.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/
git commit -m "feat: python project skeleton with FastAPI health check"
```

---

### Task 0.2: Angular Project Skeleton

**Files:**
- Create: `frontend/` (Angular CLI output)
- Create: `frontend/src/app/core/`
- Create: `frontend/src/app/shared/`
- Create: `frontend/src/app/features/`

**Step 1: Scaffold Angular project**

```bash
cd frontend
npx @angular/cli@latest new soc-ui --directory . --routing --style scss --ssr false --skip-git
```

**Step 2: Install Angular Material**

```bash
cd frontend && npx ng add @angular/material --skip-confirmation
```

**Step 3: Create feature module directories**

```bash
mkdir -p frontend/src/app/core/services
mkdir -p frontend/src/app/core/interceptors
mkdir -p frontend/src/app/core/guards
mkdir -p frontend/src/app/shared/components
mkdir -p frontend/src/app/shared/pipes
mkdir -p frontend/src/app/features/info
mkdir -p frontend/src/app/features/users
mkdir -p frontend/src/app/features/detections
mkdir -p frontend/src/app/features/cases
mkdir -p frontend/src/app/features/events
mkdir -p frontend/src/app/features/assistant
mkdir -p frontend/src/app/features/config
mkdir -p frontend/src/app/features/login
```

**Step 4: Verify build**

Run: `cd frontend && npx ng build`
Expected: Build succeeds with 0 errors

**Step 5: Run default tests**

Run: `cd frontend && npx ng test --watch=false --browsers=ChromeHeadless`
Expected: PASS (default app component test)

**Step 6: Commit**

```bash
git add frontend/
git commit -m "feat: angular project skeleton with Material and feature module structure"
```

---

### Task 0.3: Characterization Test Infrastructure

**Files:**
- Create: `backend/tests/characterization/__init__.py`
- Create: `backend/tests/characterization/conftest.py`
- Create: `backend/tests/characterization/golden_masters/`
- Create: `backend/scripts/capture_golden_masters.py`

**Step 1: Write golden master capture script**

This script runs against the live Go server and records request/response pairs.

```python
# backend/scripts/capture_golden_masters.py
"""
Captures HTTP request/response pairs from the running Go server
as golden master fixtures for characterization testing.

Usage: python capture_golden_masters.py --base-url https://localhost:9822 --output tests/characterization/golden_masters/
"""
import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx


@dataclass
class GoldenMaster:
    method: str
    path: str
    request_body: dict | None
    request_headers: dict[str, str]
    status_code: int
    response_body: dict | list | str | None
    response_headers: dict[str, str]


ENDPOINTS_TO_CAPTURE = [
    ("GET", "/api/info/"),
    ("GET", "/api/config/"),
    ("GET", "/api/users/"),
    ("GET", "/api/roles/"),
    ("GET", "/api/events/"),
    ("GET", "/api/detection/"),
    ("GET", "/api/case/"),
    ("GET", "/api/jobs/"),
]


def capture(base_url: str, auth_token: str, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    client = httpx.Client(
        base_url=base_url,
        headers={"Authorization": f"Bearer {auth_token}"},
        verify=False,
        timeout=30.0,
    )

    for method, path in ENDPOINTS_TO_CAPTURE:
        try:
            resp = client.request(method, path)
            try:
                body = resp.json()
            except Exception:
                body = resp.text

            gm = GoldenMaster(
                method=method,
                path=path,
                request_body=None,
                request_headers=dict(client.headers),
                status_code=resp.status_code,
                response_body=body,
                response_headers=dict(resp.headers),
            )

            filename = f"{method.lower()}_{path.strip('/').replace('/', '_')}.json"
            (output_dir / filename).write_text(json.dumps(asdict(gm), indent=2, default=str))
            print(f"OK {method} {path} -> {resp.status_code}")
        except Exception as e:
            print(f"FAIL {method} {path} -> {e}", file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--auth-token", required=True)
    parser.add_argument("--output", default="tests/characterization/golden_masters/")
    args = parser.parse_args()
    capture(args.base_url, args.auth_token, Path(args.output))
```

**Step 2: Write characterization test conftest**

```python
# backend/tests/characterization/conftest.py
import json
from pathlib import Path

import pytest

GOLDEN_DIR = Path(__file__).parent / "golden_masters"


@pytest.fixture
def golden_masters() -> dict[str, dict]:
    masters = {}
    if not GOLDEN_DIR.exists():
        return masters
    for f in GOLDEN_DIR.glob("*.json"):
        masters[f.stem] = json.loads(f.read_text())
    return masters


def normalize_response(body: dict | list | str | None) -> dict | list | str | None:
    """Strip non-deterministic fields before comparison."""
    if isinstance(body, dict):
        skip = {"srvToken", "createTime", "updateTime", "timestamp", "version"}
        return {k: normalize_response(v) for k, v in body.items() if k not in skip}
    if isinstance(body, list):
        return [normalize_response(item) for item in body]
    return body
```

**Step 3: Write a sample characterization test**

```python
# backend/tests/characterization/test_api_shape.py
"""
These tests verify the FastAPI responses match the structure
captured from the Go server. They skip if no golden masters exist.
"""
import pytest


@pytest.mark.skip(reason="No golden masters captured yet - run capture script against Go server first")
async def test_info_endpoint_matches_golden_master(client, golden_masters):
    gm = golden_masters.get("get_api_info")
    if gm is None:
        pytest.skip("No golden master for GET /api/info/")
    resp = await client.get("/api/info/")
    assert resp.status_code == gm["status_code"]
```

**Step 4: Verify tests collect**

Run: `cd backend && pytest tests/characterization/ -v --collect-only`
Expected: 1 test collected, marked as skip

**Step 5: Commit**

```bash
git add backend/tests/characterization/ backend/scripts/
git commit -m "feat: characterization test infrastructure with golden master capture"
```

---

### Task 0.4: OpenAPI Spec from Go Server

**Files:**
- Create: `docs/api/openapi-go-captured.yaml`

**Step 1: Extract route list from Go code**

Reference `server/server.go:79-120` for all `RegisterXRoutes` calls. Cross-reference each `*handler.go` file for exact routes.

Manually create an OpenAPI spec capturing the current API surface. This becomes the contract the FastAPI server must satisfy.

```yaml
# docs/api/openapi-go-captured.yaml
openapi: "3.1.0"
info:
  title: SecurityOnion SOC API (captured from Go)
  version: "1.0.0"
paths:
  /api/health:
    get:
      operationId: health
      responses:
        "200":
          description: OK
  /api/info/:
    get:
      operationId: getInfo
      responses:
        "200":
          description: System info, license, version, tools
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Info"
  /api/config/:
    get:
      operationId: getConfig
      parameters:
        - name: advanced
          in: query
          schema:
            type: boolean
            default: false
      responses:
        "200":
          description: List of settings
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: "#/components/schemas/Setting"
    put:
      operationId: putSetting
      requestBody:
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/Setting"
      responses:
        "200":
          description: Setting updated
  /api/users/:
    get:
      operationId: getUsers
      responses:
        "200":
          description: List of users
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: "#/components/schemas/User"
    post:
      operationId: createUser
      requestBody:
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/User"
      responses:
        "200":
          description: User created
  /api/users/{id}:
    put:
      operationId: updateUser
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
            pattern: "^[A-Za-z0-9-]{36}$"
      responses:
        "200":
          description: User updated
    delete:
      operationId: deleteUser
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: User deleted
  /api/users/{id}/password:
    put:
      operationId: resetPassword
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Password reset
  /api/users/{id}/role/{role}:
    post:
      operationId: addRole
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
        - name: role
          in: path
          required: true
          schema:
            type: string
            pattern: "^[A-Za-z0-9-_]{3,50}$"
      responses:
        "200":
          description: Role added
    delete:
      operationId: deleteRole
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
        - name: role
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Role removed
  /api/roles/:
    get:
      operationId: getRoles
      responses:
        "200":
          description: List of roles
  /api/events/:
    get:
      operationId: getEvents
      parameters:
        - name: query
          in: query
          schema:
            type: string
        - name: range
          in: query
          schema:
            type: string
        - name: zone
          in: query
          schema:
            type: string
        - name: format
          in: query
          schema:
            type: string
        - name: metricLimit
          in: query
          schema:
            type: integer
        - name: eventLimit
          in: query
          schema:
            type: integer
      responses:
        "200":
          description: Event search results
  /api/events/ack:
    post:
      operationId: ackEvents
      responses:
        "200":
          description: Events acknowledged
  /api/detection/{id}:
    get:
      operationId: getDetection
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Detection details
    put:
      operationId: updateDetection
      responses:
        "200":
          description: Detection updated
    delete:
      operationId: deleteDetection
      responses:
        "200":
          description: Detection deleted
  /api/detection/:
    post:
      operationId: createDetection
      responses:
        "200":
          description: Detection created
  /api/detection/{id}/duplicate:
    post:
      operationId: duplicateDetection
      responses:
        "200":
          description: Detection duplicated
  /api/detection/{id}/comment:
    post:
      operationId: createDetectionComment
      responses:
        "200":
          description: Comment created
    get:
      operationId: getDetectionComments
      responses:
        "200":
          description: List of comments
  /api/detection/bulk/{newStatus}:
    post:
      operationId: bulkUpdateDetection
      responses:
        "202":
          description: Bulk update started
  /api/detection/sync/{engine}/{type}:
    post:
      operationId: syncDetections
      responses:
        "200":
          description: Sync started
  /api/case/:
    post:
      operationId: createCase
      responses:
        "200":
          description: Case created
    get:
      operationId: getCases
      responses:
        "200":
          description: List of cases
    put:
      operationId: updateCase
      responses:
        "200":
          description: Case updated
  /api/case/{id}:
    get:
      operationId: getCase
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Case details
  /api/case/comments:
    post:
      operationId: createCaseComment
      responses:
        "200":
          description: Comment created
    get:
      operationId: getCaseComments
      responses:
        "200":
          description: List of comments
    put:
      operationId: updateCaseComment
      responses:
        "200":
          description: Comment updated
    delete:
      operationId: deleteCaseComment
      responses:
        "200":
          description: Comment deleted
  /api/case/events:
    post:
      operationId: attachCaseEvents
      responses:
        "202":
          description: Event attachment started
    get:
      operationId: getCaseEvents
      responses:
        "200":
          description: List of related events
    delete:
      operationId: deleteCaseEvent
      responses:
        "200":
          description: Event unlinked
  /api/case/artifacts/{groupType}:
    get:
      operationId: getArtifacts
      responses:
        "200":
          description: List of artifacts
  /api/case/history:
    get:
      operationId: getCaseHistory
      responses:
        "200":
          description: Audit history
  /api/assistant/chat:
    post:
      operationId: postChat
      responses:
        "200":
          description: Chat response (or SSE stream)
  /api/assistant/sessions:
    get:
      operationId: getSessions
      responses:
        "200":
          description: List of sessions
  /api/assistant/sessions/{sessionId}:
    put:
      operationId: updateSession
      responses:
        "200":
          description: Session updated
    delete:
      operationId: deleteSession
      responses:
        "200":
          description: Session deleted
  /api/jobs/:
    get:
      operationId: getJobs
      responses:
        "200":
          description: List of jobs
  /api/stream:
    get:
      operationId: stream
      description: WebSocket upgrade for real-time events
      responses:
        "101":
          description: Switching protocols
  /api/node:
    get:
      operationId: getNodes
      responses:
        "200":
          description: List of nodes
  /api/grid:
    get:
      operationId: getGrid
      responses:
        "200":
          description: Grid status
  /api/gridmembers:
    get:
      operationId: getGridMembers
      responses:
        "200":
          description: Grid member list

components:
  schemas:
    Info:
      type: object
      properties:
        version:
          type: string
        license:
          type: string
        licenseKey:
          type: string
        licenseStatus:
          type: string
        elasticVersion:
          type: string
        userId:
          type: string
        timezones:
          type: array
          items:
            type: string
        srvToken:
          type: string
    Setting:
      type: object
      properties:
        id:
          type: string
        value:
          type: string
        nodeId:
          type: string
    User:
      type: object
      properties:
        id:
          type: string
        email:
          type: string
        firstName:
          type: string
        lastName:
          type: string
        note:
          type: string
        roles:
          type: array
          items:
            type: string
        status:
          type: string
```

**Step 2: Commit**

```bash
git add docs/api/
git commit -m "docs: captured OpenAPI spec from Go server API surface"
```

---

## Phase 1: First Vertical Slice — `/api/info` (End-to-End)

This is the simplest endpoint. We build it fully: domain model → port → service → API route → Angular component. This proves the architecture works.

### Task 1.1: Info Domain Model

**Files:**
- Create: `backend/src/domain/info.py`
- Test: `backend/tests/domain/test_info.py`

Reference: `model/info.go` — the `Info` struct.

**Step 1: Write the failing test**

```python
# backend/tests/domain/test_info.py
from src.domain.info import Info, ClientParameters


def test_info_creation():
    info = Info(
        version="1.0.0",
        license="Elastic License 2.0",
        license_key="",
        license_status="active",
        elastic_version="8.15.0",
        user_id="abc-123",
        timezones=["UTC", "US/Eastern"],
        srv_token="token123",
        force_user_otp=False,
        mgmt_mac="",
        parameters=None,
    )
    assert info.version == "1.0.0"
    assert info.timezones == ["UTC", "US/Eastern"]
    assert info.force_user_otp is False


def test_info_serialization_uses_camel_case():
    info = Info(
        version="1.0.0",
        license="",
        license_key="",
        license_status="",
        elastic_version="",
        user_id="",
        timezones=[],
        srv_token="",
        force_user_otp=False,
        mgmt_mac="",
        parameters=None,
    )
    data = info.model_dump(by_alias=True)
    assert "srvToken" in data
    assert "forceUserOtp" in data
    assert "elasticVersion" in data
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/domain/test_info.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.domain.info'`

**Step 3: Write minimal implementation**

```python
# backend/src/domain/info.py
from pydantic import BaseModel, ConfigDict, Field


class ClientParameters(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class Info(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    version: str = ""
    license: str = ""
    license_key: str = Field(default="", alias="licenseKey")
    license_status: str = Field(default="", alias="licenseStatus")
    elastic_version: str = Field(default="", alias="elasticVersion")
    user_id: str = Field(default="", alias="userId")
    timezones: list[str] = Field(default_factory=list)
    srv_token: str = Field(default="", alias="srvToken")
    force_user_otp: bool = Field(default=False, alias="forceUserOtp")
    mgmt_mac: str = Field(default="", alias="mgmtMac")
    parameters: ClientParameters | None = None
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/domain/test_info.py -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add backend/src/domain/info.py backend/tests/domain/
git commit -m "feat: Info domain model with camelCase serialization"
```

---

### Task 1.2: Info Port (Protocol Interface)

**Files:**
- Create: `backend/src/ports/info.py`
- Test: `backend/tests/ports/test_info_port.py`

Reference: `server/infohandler.go` — the handler calls `Datastore.GetNodes()` and `Userstore.GetUserById()`.

**Step 1: Write the failing test**

```python
# backend/tests/ports/test_info_port.py
from src.ports.info import InfoProvider


def test_info_provider_is_protocol():
    """InfoProvider must be a Protocol so adapters don't need to inherit."""
    import typing
    assert typing.runtime_checkable(InfoProvider) or hasattr(InfoProvider, '__protocol_attrs__')


def test_fake_provider_satisfies_protocol():
    class FakeInfoProvider:
        async def get_version(self) -> str:
            return "1.0.0"

        async def get_elastic_version(self) -> str:
            return "8.15.0"

        async def get_license_info(self) -> tuple[str, str, str]:
            return ("Elastic License 2.0", "", "active")

        async def get_timezones(self) -> list[str]:
            return ["UTC"]

        async def get_mgmt_mac(self) -> str:
            return ""

    provider = FakeInfoProvider()
    assert isinstance(provider, InfoProvider)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/ports/test_info_port.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# backend/src/ports/info.py
from typing import Protocol, runtime_checkable


@runtime_checkable
class InfoProvider(Protocol):
    async def get_version(self) -> str: ...
    async def get_elastic_version(self) -> str: ...
    async def get_license_info(self) -> tuple[str, str, str]: ...
    async def get_timezones(self) -> list[str]: ...
    async def get_mgmt_mac(self) -> str: ...
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/ports/test_info_port.py -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add backend/src/ports/info.py backend/tests/ports/
git commit -m "feat: InfoProvider port protocol"
```

---

### Task 1.3: User Port (Protocol Interface)

**Files:**
- Create: `backend/src/ports/users.py`
- Create: `backend/src/domain/user.py`
- Test: `backend/tests/domain/test_user.py`

Reference: `model/user.go` — User struct. `server/userstore.go` — Userstore interface.

**Step 1: Write the failing test**

```python
# backend/tests/domain/test_user.py
from src.domain.user import User


def test_user_creation():
    user = User(
        id="abc-123-def-456-ghi-789-jkl-012-mno",
        email="analyst@soc.local",
        first_name="Jane",
        last_name="Doe",
        roles=["analyst"],
        status="active",
    )
    assert user.email == "analyst@soc.local"
    assert user.roles == ["analyst"]


def test_user_serialization_camel_case():
    user = User(id="x", email="a@b.c", first_name="A", last_name="B")
    data = user.model_dump(by_alias=True)
    assert "firstName" in data
    assert "lastName" in data
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/domain/test_user.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# backend/src/domain/user.py
from pydantic import BaseModel, ConfigDict, Field


class User(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = ""
    email: str = ""
    first_name: str = Field(default="", alias="firstName")
    last_name: str = Field(default="", alias="lastName")
    note: str = ""
    roles: list[str] = Field(default_factory=list)
    status: str = ""
    totp_status: str = Field(default="", alias="totpStatus")
    webauthn_status: str = Field(default="", alias="webauthnStatus")
```

```python
# backend/src/ports/users.py
from typing import Protocol, runtime_checkable

from src.domain.user import User


@runtime_checkable
class Userstore(Protocol):
    async def get_users(self) -> list[User]: ...
    async def get_user_by_id(self, user_id: str) -> User | None: ...
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/domain/test_user.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/domain/user.py backend/src/ports/users.py backend/tests/domain/test_user.py
git commit -m "feat: User domain model and Userstore port"
```

---

### Task 1.4: RBAC Port

**Files:**
- Create: `backend/src/ports/auth.py`
- Test: `backend/tests/ports/test_auth_port.py`

Reference: `rbac/authorizer.go` — Authorizer interface.

**Step 1: Write the failing test**

```python
# backend/tests/ports/test_auth_port.py
import pytest
from src.ports.auth import Authorizer, Unauthorized


def test_unauthorized_is_exception():
    err = Unauthorized("detections", "write")
    assert isinstance(err, Exception)
    assert "detections" in str(err)


async def test_fake_authorizer_allows():
    class AllowAll:
        async def check_authorized(self, user_id: str, operation: str, resource: str) -> None:
            pass

    auth = AllowAll()
    assert isinstance(auth, Authorizer)
    await auth.check_authorized("user1", "read", "detections")


async def test_fake_authorizer_denies():
    class DenyAll:
        async def check_authorized(self, user_id: str, operation: str, resource: str) -> None:
            raise Unauthorized(resource, operation)

    auth = DenyAll()
    assert isinstance(auth, Authorizer)
    with pytest.raises(Unauthorized):
        await auth.check_authorized("user1", "write", "detections")
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/ports/test_auth_port.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# backend/src/ports/auth.py
from typing import Protocol, runtime_checkable


class Unauthorized(Exception):
    def __init__(self, resource: str, operation: str):
        self.resource = resource
        self.operation = operation
        super().__init__(f"Unauthorized: {operation} on {resource}")


@runtime_checkable
class Authorizer(Protocol):
    async def check_authorized(self, user_id: str, operation: str, resource: str) -> None: ...
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/ports/test_auth_port.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add backend/src/ports/auth.py backend/tests/ports/test_auth_port.py
git commit -m "feat: Authorizer port and Unauthorized exception"
```

---

### Task 1.5: Info Service

**Files:**
- Create: `backend/src/services/info_service.py`
- Test: `backend/tests/services/test_info_service.py`

Reference: `server/infohandler.go:38-100` — the `getInfo` handler function. Business logic to extract into service.

**Step 1: Write the failing test**

```python
# backend/tests/services/test_info_service.py
import pytest
from src.services.info_service import InfoService
from src.domain.info import Info
from src.domain.user import User


class FakeInfoProvider:
    async def get_version(self) -> str:
        return "2.4.110"

    async def get_elastic_version(self) -> str:
        return "8.15.3"

    async def get_license_info(self) -> tuple[str, str, str]:
        return ("Elastic License 2.0", "key123", "active")

    async def get_timezones(self) -> list[str]:
        return ["UTC", "US/Eastern", "Europe/London"]

    async def get_mgmt_mac(self) -> str:
        return "00:11:22:33:44:55"


class FakeUserstore:
    async def get_users(self) -> list[User]:
        return []

    async def get_user_by_id(self, user_id: str) -> User | None:
        if user_id == "user-1":
            return User(id="user-1", email="analyst@soc.local", first_name="Jane", last_name="Doe")
        return None


async def test_get_info_returns_populated_info():
    service = InfoService(
        info_provider=FakeInfoProvider(),
        userstore=FakeUserstore(),
    )
    info = await service.get_info(user_id="user-1")
    assert info.version == "2.4.110"
    assert info.elastic_version == "8.15.3"
    assert info.license == "Elastic License 2.0"
    assert info.user_id == "user-1"
    assert len(info.timezones) == 3
    assert info.mgmt_mac == "00:11:22:33:44:55"


async def test_get_info_unknown_user():
    service = InfoService(
        info_provider=FakeInfoProvider(),
        userstore=FakeUserstore(),
    )
    info = await service.get_info(user_id="nonexistent")
    assert info.user_id == "nonexistent"
    assert info.force_user_otp is False
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/services/test_info_service.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# backend/src/services/info_service.py
from src.domain.info import Info
from src.ports.info import InfoProvider
from src.ports.users import Userstore


class InfoService:
    def __init__(self, info_provider: InfoProvider, userstore: Userstore):
        self._info = info_provider
        self._users = userstore

    async def get_info(self, user_id: str) -> Info:
        version = await self._info.get_version()
        elastic_version = await self._info.get_elastic_version()
        license_name, license_key, license_status = await self._info.get_license_info()
        timezones = await self._info.get_timezones()
        mgmt_mac = await self._info.get_mgmt_mac()

        user = await self._users.get_user_by_id(user_id)
        force_otp = False
        if user is not None:
            force_otp = user.totp_status == "forced"

        return Info(
            version=version,
            license=license_name,
            license_key=license_key,
            license_status=license_status,
            elastic_version=elastic_version,
            user_id=user_id,
            timezones=timezones,
            srv_token="",
            force_user_otp=force_otp,
            mgmt_mac=mgmt_mac,
        )
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/services/test_info_service.py -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add backend/src/services/info_service.py backend/tests/services/
git commit -m "feat: InfoService with provider and userstore injection"
```

---

### Task 1.6: Shared Request Context + Auth Middleware

**Files:**
- Create: `backend/src/shared/context.py`
- Create: `backend/src/shared/middleware.py`
- Test: `backend/tests/shared/test_context.py`

Reference: `web/host.go` — context keys, `web/middleware.go` — auth middleware.

**Step 1: Write the failing test**

```python
# backend/tests/shared/test_context.py
import pytest
from src.shared.context import RequestContext


def test_request_context_creation():
    ctx = RequestContext(requestor_id="user-1", username="analyst@soc.local")
    assert ctx.requestor_id == "user-1"
    assert ctx.username == "analyst@soc.local"


def test_request_context_system_user():
    ctx = RequestContext.system()
    assert ctx.requestor_id == "00000000-0000-0000-0000-000000000000"
    assert ctx.username == "system"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/shared/test_context.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# backend/src/shared/context.py
from dataclasses import dataclass

SYSTEM_ID = "00000000-0000-0000-0000-000000000000"
AGENT_ID = "00000000-0000-0000-0000-000000000001"


@dataclass(frozen=True)
class RequestContext:
    requestor_id: str
    username: str = ""

    @classmethod
    def system(cls) -> "RequestContext":
        return cls(requestor_id=SYSTEM_ID, username="system")

    @classmethod
    def agent(cls) -> "RequestContext":
        return cls(requestor_id=AGENT_ID, username="agent")
```

```python
# backend/src/shared/middleware.py
from fastapi import Depends, HTTPException, Request

from src.shared.context import RequestContext


async def get_request_context(request: Request) -> RequestContext:
    """Extract requestor identity from request headers/cookies.
    Stub: returns a hardcoded user until auth adapters are wired."""
    user_id = request.headers.get("X-Requestor-Id", "")
    username = request.headers.get("X-Username", "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return RequestContext(requestor_id=user_id, username=username)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/shared/test_context.py -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add backend/src/shared/ backend/tests/shared/
git commit -m "feat: RequestContext and auth middleware stub"
```

---

### Task 1.7: Info API Route

**Files:**
- Create: `backend/src/api/info_routes.py`
- Test: `backend/tests/api/test_info_routes.py`

Reference: `server/infohandler.go` — route registration and handler.

**Step 1: Write the failing test**

```python
# backend/tests/api/test_info_routes.py
import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.api.info_routes import router as info_router
from src.services.info_service import InfoService
from src.domain.user import User


class FakeInfoProvider:
    async def get_version(self) -> str:
        return "2.4.110"

    async def get_elastic_version(self) -> str:
        return "8.15.3"

    async def get_license_info(self) -> tuple[str, str, str]:
        return ("Elastic License 2.0", "", "active")

    async def get_timezones(self) -> list[str]:
        return ["UTC"]

    async def get_mgmt_mac(self) -> str:
        return ""


class FakeUserstore:
    async def get_users(self) -> list[User]:
        return []

    async def get_user_by_id(self, user_id: str) -> User | None:
        return User(id=user_id, email="test@test.com")


@pytest.fixture
def test_app():
    from fastapi import FastAPI
    from src.shared.context import RequestContext
    from src.api.info_routes import get_info_service, get_context

    test_app = FastAPI()
    test_app.include_router(info_router, prefix="/api")

    service = InfoService(
        info_provider=FakeInfoProvider(),
        userstore=FakeUserstore(),
    )
    test_app.dependency_overrides[get_info_service] = lambda: service
    test_app.dependency_overrides[get_context] = lambda: RequestContext(
        requestor_id="user-1", username="test@test.com"
    )
    return test_app


@pytest.fixture
async def client(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_get_info(client):
    resp = await client.get("/api/info/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == "2.4.110"
    assert body["elasticVersion"] == "8.15.3"
    assert body["userId"] == "user-1"
    assert "timezones" in body


async def test_get_info_unauthenticated():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/info/")
        assert resp.status_code == 401
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/api/test_info_routes.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# backend/src/api/info_routes.py
from fastapi import APIRouter, Depends

from src.domain.info import Info
from src.services.info_service import InfoService
from src.shared.context import RequestContext
from src.shared.middleware import get_request_context

router = APIRouter()


def get_info_service() -> InfoService:
    raise NotImplementedError("Wire in main.py via dependency_overrides")


def get_context(ctx: RequestContext = Depends(get_request_context)) -> RequestContext:
    return ctx


@router.get("/info/", response_model=Info)
async def get_info(
    service: InfoService = Depends(get_info_service),
    ctx: RequestContext = Depends(get_context),
) -> Info:
    return await service.get_info(user_id=ctx.requestor_id)
```

**Step 4: Update main.py to include router**

```python
# backend/src/main.py
from fastapi import FastAPI

from src.api.info_routes import router as info_router

app = FastAPI(title="SecurityOnion SOC", version="0.1.0")
app.include_router(info_router, prefix="/api")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

**Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/api/test_info_routes.py -v`
Expected: PASS (2 tests)

**Step 6: Commit**

```bash
git add backend/src/api/info_routes.py backend/src/main.py backend/tests/api/
git commit -m "feat: GET /api/info/ endpoint with dependency injection"
```

---

### Task 1.8: In-Memory Info Adapter (Stub)

**Files:**
- Create: `backend/src/adapters/stub/__init__.py`
- Create: `backend/src/adapters/stub/info_provider.py`
- Test: `backend/tests/adapters/test_stub_info.py`

This stub adapter lets the app run without real integrations.

**Step 1: Write the failing test**

```python
# backend/tests/adapters/test_stub_info.py
from src.adapters.stub.info_provider import StubInfoProvider
from src.ports.info import InfoProvider


async def test_stub_satisfies_protocol():
    stub = StubInfoProvider(version="1.0.0")
    assert isinstance(stub, InfoProvider)


async def test_stub_returns_configured_values():
    stub = StubInfoProvider(version="2.4.110", elastic_version="8.15.3")
    assert await stub.get_version() == "2.4.110"
    assert await stub.get_elastic_version() == "8.15.3"
    lic, key, status = await stub.get_license_info()
    assert lic == "Elastic License 2.0"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/adapters/test_stub_info.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# backend/src/adapters/stub/info_provider.py
class StubInfoProvider:
    def __init__(
        self,
        version: str = "0.0.0-dev",
        elastic_version: str = "8.15.0",
    ):
        self._version = version
        self._elastic_version = elastic_version

    async def get_version(self) -> str:
        return self._version

    async def get_elastic_version(self) -> str:
        return self._elastic_version

    async def get_license_info(self) -> tuple[str, str, str]:
        return ("Elastic License 2.0", "", "active")

    async def get_timezones(self) -> list[str]:
        return ["UTC", "US/Eastern", "US/Central", "US/Mountain", "US/Pacific", "Europe/London"]

    async def get_mgmt_mac(self) -> str:
        return "00:00:00:00:00:00"
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/adapters/test_stub_info.py -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add backend/src/adapters/ backend/tests/adapters/
git commit -m "feat: stub InfoProvider adapter for development"
```

---

### Task 1.9: Angular Info Feature — API Service

**Files:**
- Create: `frontend/src/app/core/services/api.service.ts`
- Create: `frontend/src/app/features/info/info.service.ts`
- Create: `frontend/src/app/features/info/info.model.ts`
- Test: `frontend/src/app/features/info/info.service.spec.ts`

**Step 1: Create the API model**

```typescript
// frontend/src/app/features/info/info.model.ts
export interface Info {
  version: string;
  license: string;
  licenseKey: string;
  licenseStatus: string;
  elasticVersion: string;
  userId: string;
  timezones: string[];
  srvToken: string;
  forceUserOtp: boolean;
  mgmtMac: string;
}
```

**Step 2: Create base API service**

```typescript
// frontend/src/app/core/services/api.service.ts
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private baseUrl = '/api';

  constructor(private http: HttpClient) {}

  get<T>(path: string): Observable<T> {
    return this.http.get<T>(`${this.baseUrl}${path}`);
  }

  post<T>(path: string, body: unknown): Observable<T> {
    return this.http.post<T>(`${this.baseUrl}${path}`, body);
  }

  put<T>(path: string, body: unknown): Observable<T> {
    return this.http.put<T>(`${this.baseUrl}${path}`, body);
  }

  delete<T>(path: string): Observable<T> {
    return this.http.delete<T>(`${this.baseUrl}${path}`);
  }
}
```

**Step 3: Create info service**

```typescript
// frontend/src/app/features/info/info.service.ts
import { Injectable, signal } from '@angular/core';
import { ApiService } from '../../core/services/api.service';
import { Info } from './info.model';

@Injectable({ providedIn: 'root' })
export class InfoService {
  readonly info = signal<Info | null>(null);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  constructor(private api: ApiService) {}

  loadInfo(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.get<Info>('/info/').subscribe({
      next: (info) => {
        this.info.set(info);
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set(err.message);
        this.loading.set(false);
      },
    });
  }
}
```

**Step 4: Write the test**

```typescript
// frontend/src/app/features/info/info.service.spec.ts
import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { InfoService } from './info.service';
import { Info } from './info.model';

describe('InfoService', () => {
  let service: InfoService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(InfoService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('should load info', () => {
    const mockInfo: Info = {
      version: '2.4.110',
      license: 'Elastic License 2.0',
      licenseKey: '',
      licenseStatus: 'active',
      elasticVersion: '8.15.3',
      userId: 'user-1',
      timezones: ['UTC'],
      srvToken: '',
      forceUserOtp: false,
      mgmtMac: '',
    };

    service.loadInfo();
    const req = httpMock.expectOne('/api/info/');
    expect(req.request.method).toBe('GET');
    req.flush(mockInfo);

    expect(service.info()).toEqual(mockInfo);
    expect(service.loading()).toBe(false);
  });
});
```

**Step 5: Run test**

Run: `cd frontend && npx ng test --watch=false --browsers=ChromeHeadless --include='**/info.service.spec.ts'`
Expected: PASS

**Step 6: Commit**

```bash
git add frontend/src/app/core/ frontend/src/app/features/info/
git commit -m "feat: Angular InfoService with signal-based state"
```

---

### Task 1.10: Angular Info Component

**Files:**
- Create: `frontend/src/app/features/info/info.component.ts`
- Create: `frontend/src/app/features/info/info.component.html`
- Test: `frontend/src/app/features/info/info.component.spec.ts`

**Step 1: Create the component**

```typescript
// frontend/src/app/features/info/info.component.ts
import { Component, OnInit } from '@angular/core';
import { InfoService } from './info.service';
import { MatCardModule } from '@angular/material/card';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-info',
  standalone: true,
  imports: [CommonModule, MatCardModule, MatProgressSpinnerModule],
  templateUrl: './info.component.html',
})
export class InfoComponent implements OnInit {
  constructor(readonly infoService: InfoService) {}

  ngOnInit(): void {
    this.infoService.loadInfo();
  }
}
```

```html
<!-- frontend/src/app/features/info/info.component.html -->
@if (infoService.loading()) {
  <mat-spinner diameter="40"></mat-spinner>
} @else if (infoService.error()) {
  <mat-card appearance="outlined">
    <mat-card-content>Error: {{ infoService.error() }}</mat-card-content>
  </mat-card>
} @else if (infoService.info(); as info) {
  <mat-card>
    <mat-card-header>
      <mat-card-title>System Info</mat-card-title>
    </mat-card-header>
    <mat-card-content>
      <dl>
        <dt>Version</dt><dd>{{ info.version }}</dd>
        <dt>Elastic Version</dt><dd>{{ info.elasticVersion }}</dd>
        <dt>License</dt><dd>{{ info.license }}</dd>
        <dt>License Status</dt><dd>{{ info.licenseStatus }}</dd>
        <dt>User ID</dt><dd>{{ info.userId }}</dd>
      </dl>
    </mat-card-content>
  </mat-card>
}
```

**Step 2: Write test**

```typescript
// frontend/src/app/features/info/info.component.spec.ts
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { InfoComponent } from './info.component';

describe('InfoComponent', () => {
  let fixture: ComponentFixture<InfoComponent>;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [InfoComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    fixture = TestBed.createComponent(InfoComponent);
    httpMock = TestBed.inject(HttpTestingController);
  });

  it('should render version after loading', () => {
    fixture.detectChanges();
    const req = httpMock.expectOne('/api/info/');
    req.flush({
      version: '2.4.110',
      license: 'Test',
      licenseKey: '',
      licenseStatus: 'active',
      elasticVersion: '8.15.3',
      userId: 'u1',
      timezones: [],
      srvToken: '',
      forceUserOtp: false,
      mgmtMac: '',
    });
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent;
    expect(text).toContain('2.4.110');
    expect(text).toContain('8.15.3');
  });
});
```

**Step 3: Run tests**

Run: `cd frontend && npx ng test --watch=false --browsers=ChromeHeadless --include='**/info.component.spec.ts'`
Expected: PASS

**Step 4: Add route**

```typescript
// In frontend/src/app/app.routes.ts, add:
{ path: 'info', loadComponent: () => import('./features/info/info.component').then(m => m.InfoComponent) },
```

**Step 5: Commit**

```bash
git add frontend/src/app/features/info/ frontend/src/app/app.routes.ts
git commit -m "feat: Angular info page with Material card display"
```

---

## Phase 2: Auth + RBAC Foundation

### Task 2.1: RBAC Domain Model

**Files:**
- Create: `backend/src/domain/rbac.py`
- Test: `backend/tests/domain/test_rbac.py`

Reference: `rbac/` directory, `server/authorization.go`.

Implement: `Permission` (operation + resource), `Role` (name + list of permissions). Test that role contains permission, role serialization.

---

### Task 2.2: RBAC Port + Allow-All Stub

**Files:**
- Create: `backend/src/ports/auth.py` (extend with role-aware methods)
- Create: `backend/src/adapters/stub/authorizer.py`
- Test: `backend/tests/adapters/test_stub_authorizer.py`

Implement: `AllowAllAuthorizer` for dev mode, wire into `Depends()` chain. Test: all operations pass. This unblocks every subsequent route.

---

### Task 2.3: Auth Middleware — Require Auth Header

**Files:**
- Modify: `backend/src/shared/middleware.py`
- Test: `backend/tests/shared/test_middleware.py`

Implement: Extract bearer token from `Authorization` header, decode JWT (stub), populate `RequestContext`. Test: missing header → 401, valid header → context populated.

---

### Task 2.4: RBAC Dependency — Route-Level Authorization

**Files:**
- Create: `backend/src/shared/rbac.py`
- Test: `backend/tests/shared/test_rbac_dependency.py`

Implement: `require_permission("resource", "operation")` → returns a `Depends()` callable that calls `Authorizer.check_authorized`. Test: allowed → passes, denied → 403.

---

### Task 2.5: Angular Auth Interceptor + Guard

**Files:**
- Create: `frontend/src/app/core/interceptors/auth.interceptor.ts`
- Create: `frontend/src/app/core/guards/auth.guard.ts`
- Test: both `.spec.ts` files

Implement: Interceptor adds bearer token to all `/api/` requests. Guard redirects to `/login` if no token. Test with HttpTestingController.

---

## Phase 3: Core Domain Models (Port from Go)

Each task follows the same pattern: write failing test for the Pydantic model, implement, pass.

### Task 3.1: Detection Domain Model

Reference: `model/detection.go` — Detection, Override, AiFields, Severity enum, Engine enum, Language enum.

**Files:** `backend/src/domain/detection.py`, `backend/tests/domain/test_detection.py`

Key points:
- Severity as Python `StrEnum`: unknown, low, medium, high, critical
- Engine as `StrEnum`: suricata, strelka, elastalert
- Language as `StrEnum`: sigma, suricata, yara
- Override with per-engine validation (reference `model/detection.go:130-250`)
- Detection.validate() method

---

### Task 3.2: Case Domain Model

Reference: `model/case.go` — Case, Comment, RelatedEvent, Artifact, ArtifactStream, Auditable base.

**Files:** `backend/src/domain/case.py`, `backend/tests/domain/test_case.py`

Key points:
- Auditable as a base Pydantic model (id, create_time, update_time, user_id)
- Case embeds Auditable
- ArtifactStream with hash computation (MD5, SHA1, SHA256)

---

### Task 3.3: Event Domain Model

Reference: `model/event.go` — EventSearchCriteria, EventSearchResults, EventRecord, EventAckCriteria.

**Files:** `backend/src/domain/event.py`, `backend/tests/domain/test_event.py`

---

### Task 3.4: Query DSL Model

Reference: `model/query.go` — Query parser with segments (search, groupby, table, sort).

**Files:** `backend/src/domain/query.py`, `backend/tests/domain/test_query.py`

This is complex: the Go code has a state-machine parser. Replicate with tests for quoted terms, grouped terms, escaped characters.

---

### Task 3.5: Node Domain Model

Reference: `model/node.go` — Node (80+ fields), NodeStatus, ProcessStatus.

**Files:** `backend/src/domain/node.py`, `backend/tests/domain/test_node.py`

---

### Task 3.6: Assistant Domain Model

Reference: `model/assistant.go` — Message, ContentBlock, ToolResult, ChatRequest, SessionUsage.

**Files:** `backend/src/domain/assistant.py`, `backend/tests/domain/test_assistant.py`

Key: custom JSON serialization for Message (string vs ContentBlock union).

---

### Task 3.7: Remaining Domain Models

Port in one task each: `Setting`, `Job`, `Packet`, `Client`, `GridMember`, `Subgrid`, `Playbook`, `Status`, `SrvToken`, `Config`.

Reference: corresponding `model/*.go` files.

---

## Phase 4: Ports + Services for Each Domain

Each domain gets: port (Protocol) → service (business logic) → API route (FastAPI router).

### Task 4.1: Detection Ports

**Files:** `backend/src/ports/detections.py`

Protocols: `Detectionstore`, `DetectionEngine` — reference `server/detectionstore.go`, `server/detectionengine.go`.

---

### Task 4.2: Detection Service

**Files:** `backend/src/services/detection_service.py`, tests

Reference: `server/detectionhandler.go` — extract business logic from handlers into service methods: `create_detection`, `update_detection`, `delete_detection`, `bulk_update`, `get_detection`, `duplicate`, `sync_engine`.

Key logic to preserve:
- Language→Engine mapping (sigma→elastalert, yara→strelka, suricata→suricata)
- Override validation per engine
- Prevent community detection creation/deletion
- Auto-disable on sync failure (return 206)
- Filter status modification (return 205)

---

### Task 4.3: Detection API Routes

**Files:** `backend/src/api/detection_routes.py`, tests

17 endpoints. Reference `server/detectionhandler.go` route registration.

---

### Task 4.4: Case Ports + Service + Routes

Reference: `server/casehandler.go` (880 lines, 30+ routes).

Split into 3 sub-tasks:
- 4.4a: Ports (`Casestore` Protocol)
- 4.4b: Service (CRUD cases, comments, events, artifacts, file upload with hashing)
- 4.4c: Routes (30+ endpoints)

---

### Task 4.5: Event Ports + Service + Routes

Reference: `server/eventhandler.go` — simpler (2 routes: search + ack).

---

### Task 4.6: Users Ports + Service + Routes

Reference: `server/usershandler.go` — 9 routes. `server/userstore.go`, `server/adminuserstore.go`.

---

### Task 4.7: Config Ports + Service + Routes

Reference: `server/confighandler.go` — 7 routes.

---

### Task 4.8: Remaining Handlers

Port each as a single task:
- Jobs/Job handler (4 routes)
- Grid/GridMembers handler (4 routes)
- Node handler (2 routes)
- Query handler (2 routes)
- Packet handler (1 route)
- Playbook handler (3 routes)
- Roles handler (2 routes)
- Clients handler (4 routes)
- Util handler (misc endpoints)

---

## Phase 5: Real-Time Features

### Task 5.1: WebSocket Infrastructure

**Files:** `backend/src/shared/websocket.py`, `backend/src/api/stream_routes.py`

Reference: `web/websockethandler.go` — WebSocket hub with pub/sub, ping/pong heartbeat.

Implement: FastAPI WebSocket endpoint at `/api/stream`, connection manager with broadcast, subscription by message kind.

---

### Task 5.2: SSE Streaming for Assistant

**Files:** `backend/src/api/assistant_routes.py`

Reference: `server/assistanthandler.go` — `PostChat` with `Accept: text/event-stream`.

Implement: `StreamingResponse` with `text/event-stream` media type. Async generator that yields SSE-formatted chunks.

---

### Task 5.3: Assistant Ports + Service

Reference: `server/assistanthandler.go`, `server/assistantstore.go`, `server/assistantmanager.go`.

Ports: `Assistantstore`, `AssistantManager`, `AssistantAdapter`.
Service: chat, tool execution, session management, usage tracking.

---

### Task 5.4: Angular WebSocket Service

**Files:** `frontend/src/app/core/services/websocket.service.ts`

Reference: `html/js/app.js:openWebsocket()` — auto-reconnect, subscribe/publish pattern.

Implement: RxJS-based WebSocket service with reconnection, typed message handling.

---

## Phase 6: Angular Feature Modules

### Task 6.1: Login Feature

Reference: `html/js/routes/login.js` (220 lines) — Ory/Kratos auth flows.

Implement: Login component with password, TOTP, and OIDC support. Auth guard integration.

---

### Task 6.2: Users Feature

Reference: `html/js/routes/users.js` (259 lines) — CRUD, roles, password.

Implement: Users list, create/edit dialog, role management, enable/disable toggle.

---

### Task 6.3: Config Feature

Reference: `html/js/routes/config.js` — settings CRUD with advanced toggle.

---

### Task 6.4: Detection Feature

Reference: `html/js/routes/detection.js` (1425 lines) — rule editor, overrides, history.

Split into sub-tasks:
- 6.4a: Detection list view with search
- 6.4b: Detection detail/edit form (per-engine fields)
- 6.4c: Override management
- 6.4d: Comment threading + history

---

### Task 6.5: Case Feature

Reference: `html/js/routes/case.js` (1129 lines) — multi-tab case management.

Split into sub-tasks:
- 6.5a: Case list + create
- 6.5b: Case detail (tabs: details, evidence, comments)
- 6.5c: Artifact upload + hash display
- 6.5d: Related events management

---

### Task 6.6: Hunt Feature

Reference: `html/js/routes/hunt.js` (3342 lines) — query builder, charts, results table.

Split into sub-tasks:
- 6.6a: Query bar with filter/groupby
- 6.6b: Results table with pagination
- 6.6c: Timeline chart (Chart.js)
- 6.6d: Event detail panel
- 6.6e: Bulk actions (escalate, acknowledge)

---

### Task 6.7: Assistant Feature

Reference: `html/js/routes/assistant.js` (2184 lines) — AI chat with streaming.

Split into sub-tasks:
- 6.7a: Session list sidebar
- 6.7b: Chat message display (markdown, code blocks)
- 6.7c: Streaming message input
- 6.7d: Tool execution panels
- 6.7e: Model selector + token/credit tracking

---

### Task 6.8: I18n System

Reference: `html/js/i18n.js` (2300+ keys).

Implement: Angular i18n or ngx-translate with the same key structure. Export keys from Vue i18n file.

---

## Phase 7: Integration & Hardening

### Task 7.1: Schemathesis API Fuzz Testing

Run Schemathesis against the FastAPI server using the OpenAPI spec from Task 0.4.

```bash
cd backend && schemathesis run http://localhost:8000/openapi.json --checks all
```

---

### Task 7.2: Docker Build

**Files:** `Dockerfile.new`

Multi-stage: Python backend + Angular frontend build. Serve Angular via FastAPI static files or nginx.

---

### Task 7.3: Characterization Test Replay

Capture golden masters from running Go server (Task 0.3 script). Run them against FastAPI server. Fix all divergences.

---

### Task 7.4: Load Testing

Baseline Go server performance. Compare FastAPI. Identify endpoints that need optimization (connection pooling, caching, async).

---

## Execution Order & Dependencies

```
Phase 0 (scaffolding)     → no deps, do first
Phase 1 (info slice)      → depends on Phase 0
Phase 2 (auth/RBAC)       → depends on Phase 0
Phase 3 (domain models)   → depends on Phase 0, can parallel with Phase 2
Phase 4 (ports/services)  → depends on Phase 2 + 3
Phase 5 (real-time)       → depends on Phase 4
Phase 6 (Angular features)→ depends on Phase 4 (needs API), can start after Phase 1
Phase 7 (hardening)       → depends on all above
```

**Parallelizable work:**
- Phase 2 (auth) + Phase 3 (domain models) can run in parallel
- Within Phase 3, all model tasks are independent
- Within Phase 4, each domain's port+service+route is independent after auth is done
- Phase 6 Angular tasks can start as soon as corresponding Phase 4 API routes exist
