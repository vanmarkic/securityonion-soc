# Prompt: Plan the 5 Core Adapters

> Copy this into a new Claude Code session to plan and implement the 5 mandatory/core adapters.

---

## Prompt

Plan and implement the 5 core adapters for the securityonion-soc FastAPI rewrite. These are the minimum needed for a production-equivalent deployment.

### Context

The rewrite lives on branch `rewrite/v4` in `/Users/dragan/Documents/securityonion-soc`. The backend is at `backend/` with:
- 116 API routes across 19 handler groups (all implemented)
- 20 domain models with validation/business logic
- 11 port Protocols in `src/ports/` — these are the interfaces each adapter must satisfy
- 866 passing unit tests
- Architecture: domain/ → ports/ → services/ → api/ → adapters/

All adapters are currently stubbed. The Go source code is in the same repo for reference.

### The 5 Adapters (in implementation order)

#### 1. StaticKeyAuth (Tier 0 — server won't boot without it)
- **Go source:** `server/modules/statickeyauth/statickeyauthimpl.go` (~120 LOC)
- **Implements:** FastAPI middleware/dependency that validates the `Authorization` header against a configured API key
- **Behavior:** If key starts with "Bearer ", skip API key check and fall through to anonymous CIDR check. If raw key matches configured key, allow. If IP is in anonymous CIDR, allow. Otherwise 401.
- **Config:** `api_key: str`, `anonymous_cidr: str` (supports `*` for skip-all, or CIDR like `0.0.0.0/0`)
- **Wire into:** Replace the current stub `get_request_context()` in `src/shared/middleware.py`
- **Test with:** The Go test at `server/modules/statickeyauth/statickeyauth_test.go`

#### 2. FileDatastore (Tier 0 — needed for jobs/nodes)
- **Go source:** `server/modules/filedatastore/` (~400 LOC across 5 files)
- **Implements:** `Datastore` Protocol from `src/ports/jobs.py` and `src/ports/grid.py`
- **Behavior:** File-based storage. Jobs stored as JSON files in a configured directory. Nodes stored in memory with file persistence. Packets served from PCAP files.
- **Config:** `job_dir: str` (path to jobs directory)
- **Key methods:** CreateJob, GetJob, GetJobs, AddJob, UpdateJob, DeleteJob, GetNodes, AddNode, UpdateNode, GetPackets, SaveJobStream, GetJobStream
- **Test with:** The Go tests at `server/modules/filedatastore/filedatastore_test.go`

#### 3. Elasticsearch (Tier 1 — unlocks 80% of the UI)
- **Go source:** `server/modules/elastic/` (21 files, ~15,800 LOC — this is the big one)
- **Implements:** `Eventstore`, `Casestore`, `Detectionstore`, `Assistantstore` Protocols
- **Behavior:** All CRUD operations against Elasticsearch indices. Event search with aggregations, case management with audit trails, detection storage, assistant chat history.
- **Dependencies:** `elasticsearch[async]` Python package, running Elasticsearch instance
- **Key complexity:** Query building (translate our Query DSL to Elasticsearch DSL), bulk indexing, scroll API for large result sets, index management
- **Config:** `host: str`, `username: str`, `password: str`, `verify_certs: bool`
- **Approach:** Start with Eventstore (search + ack), then Casestore, then Detectionstore, then Assistantstore. Each is independently testable.
- **Test with:** Docker Compose with Elasticsearch, integration tests against real instance

#### 4. StaticRBAC (Tier 1 — real permission enforcement)
- **Go source:** `server/modules/staticrbac/` (~200 LOC)
- **Implements:** `Rolestore` and `Authorizer` Protocols from `src/ports/roles.py` and `src/ports/auth.py`
- **Behavior:** Reads role definitions from YAML/JSON files. Maps users to roles, roles to permissions. `CheckAuthorized()` verifies user has required permission for operation+target.
- **Config:** Path to roles directory containing role definition files
- **Reference:** `rbac/permissions` and `rbac/roles` directories in the Go repo for the file format
- **Test with:** The Go tests at `server/modules/staticrbac/staticrbac_test.go`

#### 5. Kratos (Tier 1 — real user management)
- **Go source:** `server/modules/kratos/` (10 files, ~800 LOC)
- **Implements:** `Userstore` Protocol from `src/ports/users.py` — **READS ONLY**
  (list users, get user by ID). **CORRECTION (verified 2026-05-30):** Kratos does
  NOT implement `AdminUserstore`. The Go `kratosuserstore.go` has only
  `GetUserById`/`GetUsers`/`GetUser`. The write-side `AdminUserstore`
  (`server/adminuserstore.go`) is implemented by the **Salt** module
  (`server/modules/salt/saltstore.go`), with `AddRole`/`DeleteRole` handled by
  `staticrbac`. See `docs/plans/2026-05-30-remaining-adapters-roadmap.md`.
- **Behavior:** Communicates with the Ory Kratos API for identity reads. Maps
  Kratos identities to our User model. (Create/update/reset/enable/disable belong
  to a future Salt adapter, not Kratos.)
- **Dependencies:** `httpx` for Kratos API calls, running Kratos instance
- **Config:** `host: str`, `admin_host: str` (Kratos public + admin API URLs)
- **Test with:** Docker Compose with Kratos, integration tests against real instance

### Constraints
- Follow TDD: port Go tests first as failing Python tests, then implement
- Each adapter goes in `src/adapters/<name>/`
- Integration tests go in `tests/adapters/test_<name>.py`
- Adapters 3 and 5 need a `docker-compose.dev.yml` for local development
- Each adapter gets its own commit
- Keep diffs under 200 LOC per commit where possible (Elasticsearch will need multiple commits)
- Wire each adapter into `src/main.py` via a config-driven factory pattern

### Definition of Done
- Server boots with `StaticKeyAuth` + `FileDatastore` and serves real responses matching the golden masters at `tests/characterization/golden_masters/`
- Elasticsearch adapter passes integration tests with a real ES instance
- StaticRBAC enforces permissions that match the Go role definitions
- Kratos adapter can list/create/update users against a real Kratos instance
- All 866+ existing unit tests still pass
- Characterization tests (golden master replay) pass for all endpoints that have active adapters
