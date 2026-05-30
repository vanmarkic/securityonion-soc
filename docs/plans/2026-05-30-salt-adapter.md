# Salt Adapter Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or
> superpowers:subagent-driven-development) to implement this plan task-by-task.

**Goal:** Implement a Salt adapter that satisfies the `Configstore`,
`GridMembersstore`, and `AdminUserstore` ports by talking to SaltStack through
its file-based **relay queue**, replacing the `_UnconfiguredAdminUserstore` and
`_NullStatusstore`-adjacent placeholders so the Config, Grid-members, and
User-management write paths work end-to-end.

**Architecture:** SaltStack is **not** called via a library or `salt` subprocess.
The Go reference talks to a **salt relay**: it writes a JSON request file to a
queue directory (`/opt/so/conf/soc/queue/<reqId>_<command>`) and polls for a
sibling `<...>.response` file that an external relay daemon writes. We mirror that
with a `SaltRelayClient` seam: a real `FileQueueRelayClient` (file I/O + async
poll) for production, and an injectable fake for tests. Member/user operations
are thin command wrappers over the relay; `Configstore` is a YAML-pillar
read/write engine over `saltstackDir`. No SaltStack instance is needed to test —
exactly as Go tests pre-seed `.response` files and fixture YAML trees.

**Tech Stack:** Python 3.12, FastAPI dependency wiring, `pyyaml` (already a
transitive dep — confirm/add), `pytest`/`AsyncMock`, hexagonal ports in
`src/ports/`. Go reference: `server/modules/salt/` (`salt.go`, `saltstore.go`,
`saltstore_test.go`).

---

## SPECIFY

### Context & problem

Three ports are unimplemented; their routes currently raise "not configured":

- **`Configstore`** ([src/ports/config.py](../../backend/src/ports/config.py)) —
  `get_settings(advanced)`, `update_setting(setting, remove)`, `sync_settings()`,
  `sync_module(module, force)`. Backs the **Config** UI.
- **`GridMembersstore`** ([src/ports/gridmembers.py](../../backend/src/ports/gridmembers.py)) —
  `get_members()`, `manage_member(operation, member_id)`. Backs the **Grid
  members** page (accept/reject/delete nodes).
- **`AdminUserstore`** ([src/ports/users.py](../../backend/src/ports/users.py)) —
  `add_user`, `delete_user`, `update_profile`, `reset_password`, `enable_user`,
  `disable_user`, `add_role`, `delete_role`, `sync_users`. Backs **user
  management** writes (the read side is Kratos, already done).

In Go, `server/modules/salt/salt.go:46-49` assigns the single `Saltstore` to all
three (`Configstore`, `GridMembersstore`, `AdminUserstore`) plus
`AdminClientstore` (Hydra-adjacent — **out of scope** here).

### Scope

In scope: the three ports above, the relay client, config parsing, and wiring
into `create_app()` gated on a `salt` config block.

Out of scope: `AdminClientstore` (clients), `SendFile`/`Import` (event import —
not part of the three ports), and any real SaltStack/`docker-compose` daemon
(tests use the relay seam + fixture YAML trees).

### The salt relay mechanism (the load-bearing detail)

`Saltstore.execCommand` ([saltstore.go:58-126](../../server/modules/salt/saltstore.go#L58)):

1. `command_id = "<requestId>_<command>"`.
2. Write `args` (a `dict[str,str]`) as JSON to `<queueDir>/<command_id>`.
3. Poll `<queueDir>/<command_id>.response` until it exists or the timeout
   (`timeoutMs`, default 30 000; long ops use `longRelayTimeoutMs` 120 000) elapses.
4. On response: read, `strip()`, delete the file, return its contents.
5. No response within timeout → return error `ERROR_SALT_RELAY_DOWN`.

A `"false"` response body from any command means failure (each method maps it to
its own `ERROR_SALT_*`). This is the entire SaltStack coupling — **no salt library
needed**.

### Acceptance criteria

- `SaltConfig` parses a `salt` module block (`timeoutMs`, `longRelayTimeoutMs`,
  `saltstackDir`, `queueDir`, `bypassErrors`) with Go defaults.
- A `SaltAdapter` instance satisfies all three ports (`isinstance(adapter,
  Configstore/GridMembersstore/AdminUserstore)` is `True`).
- `get_members()` parses relay JSON into `GridMember`s; `manage_member` raises on
  `"false"`. `get_next`/auth handled by the route/service layer (not the adapter).
- All 9 `AdminUserstore` methods emit the correct `manage-user` relay args
  (verified against a fake relay) and map `"false"` → error; `add_user`/`add_role`
  trigger a Rolestore reload; `delete_user`/etc. look up the email via the
  injected `Userstore`.
- `get_settings(advanced)` parses a fixture `saltstackDir` tree
  (`default/**/defaults.yaml` + `local/**/*.sls` + `default/**/soc_*.yaml`) into
  the expected `Setting`s, mirroring Go `TestGetSettings`. `update_setting`
  writes the correct pillar YAML (mirroring the Go `TestUpdateSetting_*` cases).
- Wired into `create_app()` **only** when a `salt` block is present; the bare
  module-level `app` and default `create_app()` stay override-free/unchanged.
- Full suite still green; `ruff` + `mypy` clean on new files; characterization
  replay unaffected (config golden is `405`, an existing documented divergence).

### Test strategy

- **Relay seam:** define `SaltRelayClient` (a `Protocol` with
  `async exec_command(command_id, args, *, timeout_ms=None) -> str`). Inject a
  `FakeRelayClient` (canned `{command: response}`) into the member/user units —
  no file I/O. Test the real `FileQueueRelayClient` separately: write request,
  pre-seed `<id>.response`, assert parse + cleanup; assert `ERROR_SALT_RELAY_DOWN`
  on timeout (use `timeout_ms<=10` to skip the sleep, exactly like Go's
  `timeoutMs>10` guard).
- **Configstore:** build a temp `saltstackDir` fixture in `tmp_path` and assert
  the parsed `Setting` list. Port Go's `testdata`-equivalent YAML from the
  `TestGetSettings`/`TestUpdateSetting_*` cases.
- No external services; everything runs in the normal `pytest` suite.

### Key risks / decisions

1. **Async vs Go's blocking poll.** Make `exec_command` `async` and poll with
   `await asyncio.sleep(...)`; the adapter methods are already `async` per the
   ports. Keep the `timeout_ms<=10 → no sleep` test shortcut.
2. **Config engine size (~1000 LOC).** `GetSettings`/`UpdateSetting` and the type
   coercion (`alignType`/`forceType`/`recursivelyParseSettings`/annotations,
   [saltstore.go:240-1158](../../server/modules/salt/saltstore.go#L240)) dominate
   effort. Phases 3–4 are deliberately sub-tasked and may be split into their own
   PR. **Members + users (Phases 0–2) deliver grid + user-management UI for a
   fraction of the code — ship them first.**
3. **Adapter dependencies.** The user/role methods need the **Userstore**
   (id→email via `lookup_email_from_id`) and the **Rolestore** (reload after
   add_user/add_role). Inject both; in `create_app` reuse the already-built
   `userstore` and `rbac`.
4. **`bypassErrors`** changes `get_settings` to log-and-continue on YAML errors —
   port it as a flag, default `False`.

---

## PLAN

Implementation order ships value early: relay → grid members → user management →
config reads → config writes → wiring. Phases 0–2 are one PR; 3–4 a second.

### Phase 0 — Relay client foundation

#### Task 1: `SaltConfig`

**Files:**
- Modify: [backend/src/config.py](../../backend/src/config.py) (add `SaltConfig`
  + parse a `salt` module block, mirroring the `elastic` pattern)
- Test: `backend/tests/test_config.py`

Fields + Go defaults (`salt.go:14-43`): `timeout_ms=30_000`,
`long_relay_timeout_ms=120_000`, `saltstack_dir="/opt/so/saltstack"`,
`queue_dir="/opt/so/conf/soc/queue"`, `bypass_errors=False`. Add
`salt: SaltConfig | None = None` to `AppConfig` (None when no `salt` block, like
`elasticsearch`). TDD: a config with a `salt` block parses; absence → `None`.

#### Task 2: `SaltRelayClient` protocol + `FakeRelayClient`

**Files:**
- Create: `backend/src/adapters/salt/relay.py`
- Test: `backend/tests/adapters/salt/test_relay.py`

```python
class SaltRelayClient(Protocol):
    async def exec_command(
        self, command_id: str, args: dict[str, str], *, timeout_ms: int | None = None
    ) -> str: ...
```

Provide a `FakeRelayClient(responses: dict[str, str])` keyed by `args["command"]`
returning canned output (used by later units). TDD: fake returns the canned
string; unknown command raises.

#### Task 3: `FileQueueRelayClient` (real relay)

**Files:**
- Modify: `backend/src/adapters/salt/relay.py`
- Test: `backend/tests/adapters/salt/test_relay.py`

Port `execCommand`: write `args` as JSON to `<queue_dir>/<command_id>`, poll for
`<...>.response`, `strip()`, delete, return; timeout → raise
`SaltRelayDown("ERROR_SALT_RELAY_DOWN")`. Use `await asyncio.sleep(1)` between
polls only when `timeout_ms > 10` (test shortcut). TDD:
- pre-seed `<id>.response` → returns its stripped content and deletes it;
- no response + `timeout_ms=5` → raises `SaltRelayDown` fast;
- request file is written with the expected JSON.

**Commit:** `feat(salt): relay client (file-queue) + config`

### Phase 1 — GridMembersstore

#### Task 4: `parse_members` (port `getMembersFromJson`)

**Files:**
- Create: `backend/src/adapters/salt/members.py`
- Test: `backend/tests/adapters/salt/test_members.py`

Port `getMembersFromJson` ([saltstore.go:1133](../../server/modules/salt/saltstore.go#L1133))
→ `parse_members(output: str) -> list[GridMember]` using the existing
`new_grid_member(id, status, fingerprint)`
([domain/gridmember.py](../../backend/src/domain/gridmember.py)). TDD mirrors
Go `TestGetMembersFromJson`: valid JSON → members; malformed JSON → error; an
upstream error passes through.

#### Task 5: `SaltGridMembersstore.get_members` / `manage_member`

**Files:**
- Create: `backend/src/adapters/salt/gridmembers.py`
- Test: `backend/tests/adapters/salt/test_gridmembers.py`

`get_members`: `exec_command("<rid>_list-minions", {"command":"list-minions"})`,
`"false"` → `ERROR_SALT_MANAGE_MEMBER`, else `parse_members`. `manage_member`:
`{"command":"manage-minion","operation":op,"id":id}`, `"false"` → error. Inject a
`FakeRelayClient`. (Authorization stays in the route/service layer per hexagonal
split — do **not** port the inline `CheckAuthorized`.)

**Commit:** `feat(salt): GridMembersstore (list-minions + manage-minion)`

### Phase 2 — AdminUserstore

#### Task 6: `SaltAdminUserstore` user CRUD

**Files:**
- Create: `backend/src/adapters/salt/userstore.py`
- Test: `backend/tests/adapters/salt/test_userstore.py`

Inject `relay`, `userstore: Userstore` (for `lookup_email_from_id`), and
`rolestore` (with a `reload()`/`scan_now()`). Port the six ops
([saltstore.go:1254-1379](../../server/modules/salt/saltstore.go#L1254)) — each
sends `{"command":"manage-user","operation":<op>, "email":...}` (+ extras) and
maps `"false"` → `ERROR_SALT_MANAGE_USER`:

| method | operation | extra args |
|---|---|---|
| `add_user` | `add` | email, role=roles[0], firstName, lastName, note, password; then `rolestore.scan_now()` |
| `delete_user` | `delete` | email (looked up from id) |
| `update_profile` | `profile` | email, firstName, lastName, note |
| `reset_password` | `password` | email, password |
| `enable_user` | `enable` | email |
| `disable_user` | `disable` | email |

TDD with `FakeRelayClient` + an `AsyncMock` userstore: assert the exact relay
args dict per op, the `"false"` → error mapping, and that `add_user` calls
`rolestore.scan_now()`.

#### Task 7: `add_role` / `delete_role` / `sync_users`

**Files:**
- Modify: `backend/src/adapters/salt/userstore.py`
- Test: `backend/tests/adapters/salt/test_userstore.py`

Port [saltstore.go:1381-1460](../../server/modules/salt/saltstore.go#L1381):
`add_role` → operation `addrole` (+`role`), honors `bypass_auth_check` (no
adapter-level auth, but keep the param for the protocol), then `scan_now()`;
`delete_role` → `delrole`; `sync_users` → its `manage-user`/sync command. TDD as
above.

**Commit:** `feat(salt): AdminUserstore (manage-user ops + role + sync)`

### Phase 3 — Configstore reads (`get_settings`)

> Largest phase. Port [saltstore.go:128-660](../../server/modules/salt/saltstore.go#L137)
> incrementally; each task gets a focused YAML fixture asserting a slice of the
> behavior. Build the fixture tree once as a pytest fixture.

#### Task 8: `parse_yaml` + `Setting` annotation mapping helpers
Port `parseYaml`/`updateSettingWithAnnotation`/`castToStringArray` into
`backend/src/adapters/salt/settings.py`. TDD: a YAML string → nested dict; an
annotation block → populated `Setting` fields (description, syntax, advanced,
forcedType, options…).

#### Task 9: `recursively_parse_settings` (defaults)
Port `recursivelyParseSettings` — flatten `default/**/defaults.yaml` into
`Setting`s keyed by dotted id; set `default`/`default_available`. TDD against a
2–3 level nested fixture.

#### Task 10: local pillar overrides
Port the `local/**/*.sls` walk ([saltstore.go:174-212](../../server/modules/salt/saltstore.go#L174)):
`soc_*.sls` (global), `adv_*.sls` (advanced via `parseAdvanced`), and
`/minions/` node overrides (set `node`/`node_id`). TDD each variant.

#### Task 11: annotations + `post_process` + `filter` + `sort_settings`
Port `recursivelyParseAnnotations`, `postProcess` (no-description → advanced;
unescape jinja), `filter(advanced)`, `sortSettings`. TDD ordering + the
`advanced` filter.

#### Task 12: `SaltConfigstore.get_settings` wiring the pipeline
Compose Tasks 8–11 into `get_settings(advanced)`. TDD a full fixture
`saltstackDir` and assert the final `Setting` list — mirror Go `TestGetSettings`
(saltstore_test.go:200).

**Commit(s):** `feat(salt): Configstore get_settings (defaults+local+annotations)`

### Phase 4 — Configstore writes + sync

#### Task 13: `update_setting` (YAML pillar write)
Port `UpdateSetting`/`updateSetting`/`deleteSetting`/`writeYaml`
([saltstore.go:610-835](../../server/modules/salt/saltstore.go#L610)): locate the
pillar file (global / node / advanced), set or remove the value, write YAML.
Honor `readonly` (reject) and jinja escaping. TDD mirrors the Go
`TestUpdateSetting_*` matrix (override default, add/update/delete global & node &
advanced, jinja-escaped).

#### Task 14: type coercion (`align_type` family)
Port `alignType`/`forceType`/`alignBestGuess`/`align*List`
([saltstore.go:836-1158](../../server/modules/salt/saltstore.go#L836)) so updated
string values are written back as the correct YAML scalar/list type. TDD the
int / int-list / bool / empty-list cases from Go (`TestUpdateSetting_Align*`).

#### Task 15: `sync_settings` / `sync_module`
Port the relay-triggered sync commands. TDD with `FakeRelayClient` asserting the
emitted command + `"false"` handling.

**Commit(s):** `feat(salt): Configstore update_setting + type-align + sync`

### Phase 5 — Wiring & verification

#### Task 16: assemble `SaltAdapter` + wire into `create_app`
**Files:** Modify [backend/src/main.py](../../backend/src/main.py).
Build one `FileQueueRelayClient` from `cfg.salt` and a `SaltAdapter` composing the
three stores (sharing the relay; user store gets the already-built `userstore` +
`rbac`). Gate on `cfg.salt is not None`. Override:
`config_routes.get_config_service` → `ConfigService(salt)`;
`gridmembers_routes.get_gridmembers_service` → `GridMembersService(salt)`;
`users_routes.get_users_service` → `UsersService(userstore, salt, rbac)` (replace
`_UnconfiguredAdminUserstore`). Keep the bare `app` untouched.

#### Task 17: final verification
Run: full suite (`pytest -q`), `ruff check .`, `mypy src` (no new errors),
confirm `from src.main import app; app.dependency_overrides == {}`, and that a
`create_app()` with no `salt` block leaves these routes unwired. Update
[docs/plans/2026-05-30-remaining-adapters-roadmap.md](2026-05-30-remaining-adapters-roadmap.md)
to mark Salt done and refresh memory.

**Commit:** `feat(salt): wire Configstore + GridMembers + AdminUserstore into create_app`

---

## Suggested split

- **PR 1 (small, high value):** Phases 0–2 + a partial Task 16 (wire grid members
  + user management). Un-blocks the user-management and grid-members UI with
  ~300 LOC.
- **PR 2 (large):** Phases 3–4 + config wiring. The YAML config engine; can be its
  own SPECIFY pass if the type-coercion fidelity proves deep.
