# Remaining Adapters Roadmap (verified against Go source)

> Created 2026-05-30 after the 5 core adapters + Elasticsearch were completed and
> wired. This maps every still-unimplemented port to its **actual** Go reference
> module (verified by reading `server/`), its infrastructure dependency, its UI
> value, and a test strategy — so the next adapter is a grounded choice, not a guess.

## What is done

| Port(s) | Adapter | Go reference |
|---|---|---|
| auth (request context) | `statickeyauth` | `server/modules/statickeyauth/` |
| `JobDatastore`, grid `Datastore` (read) | `filedatastore` | `server/modules/filedatastore/` |
| `Eventstore`, `Casestore`, `Detectionstore`, `Assistantstore` | `elasticsearch` | `server/modules/elastic/` |
| `Authorizer`, `Rolestore` | `staticrbac` | `server/modules/staticrbac/` |
| `Userstore` (read: list, get-by-id) | `kratos` | `server/modules/kratos/` |
| `Configstore`, `GridMembersstore`, `AdminUserstore` + salt relay | `salt` | `server/modules/salt/` |
| `InfoProvider`, `Userstore` (dev) | `stub` | — |

Characterization replay (`tests/characterization`) now runs against the wired
`create_app()` and passes for every endpoint with an active adapter
(see `docs/characterization-divergences.md`).

**Salt adapter COMPLETE (2026-05-30):** the file-queue relay client,
`GridMembersstore`, `AdminUserstore` (PR 1), and the full `Configstore` —
`get_settings` (defaults + local pillar overrides + annotations), `update_setting`
(3-way routing + recursive set/delete + scalar/list/forcedType coercion),
`sync_settings`/`sync_module` (PR 2) — are all implemented, reviewed against the
Go source, and wired into `create_app` (gated on a `salt` config block). All three
Salt-backed ports are satisfied. No SaltStack instance is needed to test (relay
seam + fixture YAML trees). See `2026-05-30-salt-adapter.md`.

## Correction to `prompt-adapter-planning.md`

That prompt states **"Kratos implements `Userstore` and `AdminUserstore`."** This
is **wrong** and was verified against the Go source:

- `server/modules/kratos/kratosuserstore.go` implements **reads only**
  (`GetUserById`, `GetUsers`, `GetUser`). There is no `AddUser`/`DeleteUser`/etc.
- The Go `AdminUserstore` interface (`server/adminuserstore.go`) is implemented by
  **`server/modules/salt/saltstore.go`** (which shells out to SaltStack), with
  `AddRole`/`DeleteRole` handled by **`staticrbac`**.

So there is **no Kratos reference for the write-side admin operations** — building
a "Kratos admin adapter" would mean inventing un-referenced behavior. The write
path belongs to a future **Salt adapter** (below).

## Remaining ports → Go reference → cost

Ordered by a rough (value ÷ effort), infra-free first.

### Tier A — infra-free, has Go reference (do these next)

1. **`NodeDatastore` writes** — `node_service.py` needs `async update_node()->Node`
   + `get_next_job()`. Go: `filedatastore` `UpdateNode`/`GetNextJob`. Pure
   in-memory logic; unit-testable with temp dirs. Unblocks the agent **check-in
   loop** (`POST /api/node`). **← implemented 2026-05-30 (this session).**
2. **`StreamDatastore` (non-pcap parts)** — Go: `filedatastore`
   `SaveJobStream`/`GetJobStream`. `SaveJobStream` is plain file I/O (infra-free).
   `GetJobStream`'s *unwrap* path and `GetPackets` need a **PCAP parser** (Tier C).

### Tier B — has Go reference, needs external infra

3. **Salt adapter** (`server/modules/salt/`, ~1300 LOC). Backs **three** ports —
   `Configstore` (GetSettings/UpdateSetting/SyncSettings/SyncModule, the large
   YAML/type-coercion engine), `GridMembersstore` (GetMembers/ManageMember), and
   `AdminUserstore` (AddUser/Delete/UpdateProfile/ResetPassword/Enable/Disable).
   **DONE 2026-05-30 (PR 1 + PR 2):** relay client + `GridMembersstore` +
   `AdminUserstore` + the full `Configstore` (YAML-pillar read/write + type
   coercion + sync) implemented, reviewed against Go, and wired into `create_app`.
   This Tier-B item is complete.
   Needs a SaltStack master + filesystem layout; `execCommand` shells out. High UI
   value (config page, grid members, user management) but the biggest single port
   surface left. Recommend splitting per port and mocking `execCommand` for units.
4. **Hydra `Clientstore`/`AdminClientstore`** — Go: `server/modules/hydra/`
   (`hydraclientstore.go`) for OAuth client reads + `salt/saltclientadminstore.go`
   for admin. Needs Ory Hydra. UI value: the clients page (currently skipped in
   replay). Testable with mocked `httpx` (like Kratos).
5. **`Playbookstore`** — Go: `server/modules/playbook/`. Backed by ES +
   ElastAlert/Sigma. Needs ES; behavioral overlap with detections.
6. **Grid `Statusstore`** — Go: `server/modules/sostatus/` + InfluxDB. Replaces
   the `_NullStatusstore` so `/api/grid` reports real health. Needs InfluxDB.

### Tier C — behavioral / heavy ports (scope as their own projects)

7. **PCAP parser** — Go: `packet.ParsePcap`/`UnwrapPcap`. Unblocks
   `GetPackets` + `GetJobStream` unwrap. Pure logic but a real parser port.
8. **`AssistantManager`** — Go: `server/modules/assistant/`. LLM/AI manager
   (the ES `Assistantstore` persistence is already done; this is the behavioral half).
9. **Detection engines** — Go: `server/modules/{detections,elastalert,strelka,
   suricata}`. Large behavioral subsystem; the ES `Detectionstore` is already done.
10. **Real `InfoProvider`** — replaces `StubInfoProvider` with version/license/ES
    health. Small but reads from several subsystems.

## Recommendation

Tier A is the only infra-free, Go-referenced work and is now done (NodeDatastore).
The next high-value step is the **Salt adapter**, but it is large and infra-bound —
it deserves its own SPECIFY→PLAN cycle and a `docker-compose` Salt (or a mocked
`execCommand` unit strategy). Hydra `Clientstore` is the smallest Tier-B win
(mockable like Kratos) and would un-skip the clients endpoint in replay.
