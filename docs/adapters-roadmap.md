# Adapters Roadmap

> Which adapters to implement, in what order, and why.

## Current State

The FastAPI backend has 116 API routes, 20 domain models, 11 port Protocols, and 866 passing tests. All business logic is implemented. **Every adapter is currently stubbed** — ports are Protocol interfaces with no real implementations.

The Go server's module system is optional: handlers return 405 when their module isn't loaded. Our FastAPI server should behave the same way.

## Adapter Tiers

### Tier 0 — Mandatory (server boots and serves requests)

| Adapter | Implements | What it does | Go source |
|---|---|---|---|
| **StaticKeyAuth** | Auth preprocessor | API key validation + anonymous CIDR bypass. Without it, every request returns 401. | `server/modules/statickeyauth/` (2 files, ~120 LOC) |
| **FileDatastore** | Datastore | File-based storage for jobs and nodes. Needed for agent check-in loop and job CRUD. | `server/modules/filedatastore/` (~5 files, ~400 LOC) |

**With just these two, the server matches the dev config (`sensoroni.json`) and can serve `/api/info`, `/api/grid`, `/api/jobs`, `/api/node`.**

### Tier 1 — Core (production-equivalent, unlocks ~80% of UI)

| Adapter | Implements | What it does | Go source |
|---|---|---|---|
| **Elasticsearch** | Eventstore, Casestore, Detectionstore, Assistantstore | Primary data store for events, cases, detections, and AI chat history. This is the single largest adapter — the Go implementation is 21 files / ~15,800 LOC. Unlocks: event search, case management, detection CRUD, assistant sessions. | `server/modules/elastic/` (21 files) |
| **StaticRBAC** | Rolestore, Authorizer | File-based role and permission definitions. Reads role YAML files, enforces `CheckAuthorized()` calls. Without it, all auth checks are either allow-all or deny-all. | `server/modules/staticrbac/` (2 files, ~200 LOC) |
| **Kratos** | Userstore, AdminUserstore | Ory Kratos integration for user identity. Handles login flows, TOTP, WebAuthn, password management. Without it, `/api/users` returns stub data and login doesn't work. | `server/modules/kratos/` (10 files, ~800 LOC) |

**With Tier 0 + Tier 1, you have a fully functional SOC backend: analysts can search events, manage cases, write detections, manage users, and use the AI assistant.**

### Tier 2 — Integrations (full feature parity)

| Adapter | Implements | What it does | Go source |
|---|---|---|---|
| Hydra | Clientstore, AdminClientstore | OAuth2/OIDC authorization server for API clients | `server/modules/hydra/` (10 files) |
| Salt | Configstore, GridMembersstore | SaltStack remote execution for config sync and grid management | `server/modules/salt/` (7 files) |
| Suricata | DetectionEngine | Suricata IDS rule validation, sync, and management | `server/modules/suricata/` (10 files) |
| ElastAlert | DetectionEngine | Sigma rule compilation and ElastAlert rule management | `server/modules/elastalert/` (6 files) |
| Strelka | DetectionEngine | YARA rule management for file analysis | `server/modules/strelka/` (engine files) |
| TheHive | Casestore (alternative) | External case management system integration | `server/modules/thehive/` (7 files) |
| InfluxDB | Metrics | Time-series metrics collection | `server/modules/influxdb/` (files) |
| SoStatus | Statusstore | System health/status aggregation | `server/modules/sostatus/` (files) |
| Navigator | (navigation) | ATT&CK Navigator integration | `server/modules/navigator/` (3 files) |
| Playbook | Playbookstore | Playbook YAML loading from disk | `server/modules/playbook/` (files) |
| Assistant | AssistantManager | AI provider coordination (OpenAI, Gemini, SO-AI) | `server/modules/assistant/` (43 files) |

## Implementation Notes

- Each adapter implements one or more Protocol interfaces from `src/ports/`
- Adapters go in `src/adapters/<name>/` (e.g., `src/adapters/elasticsearch/`, `src/adapters/statickeyauth/`)
- Adapters should have their own integration tests in `tests/adapters/`
- The app wires adapters via FastAPI's dependency injection (`dependency_overrides` or a config-driven factory)
- Adapters that depend on external services (Elasticsearch, Kratos, Hydra) need Docker Compose for local dev
