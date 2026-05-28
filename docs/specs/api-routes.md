# API Routes Specification

> Extracted from Go source code in `server/*handler.go`. This is the contract for the Python rewrite.
> Source file: `server/server.go` registers all 19 handler groups at `/api/*` prefixes.
> All routes are mounted under an `ApiRouter` chi mux with `web.Middleware` applied.

---

## 1. CaseHandler (`/api/case`)

**Source:** `server/casehandler.go`
**Middleware:** `caseEnabled` -- returns 405 if `Casestore` is nil.
**RBAC note:** RBAC is checked at the Casestore layer, not inline in most handlers. The swagger annotations indicate the following permissions are required across all case endpoints: `cases/read`, `cases/write`, `events/read`, `events/write`.

### POST /api/case/
- **Summary:** Create Case
- **RBAC:** `cases/read`, `cases/write`, `events/read`, `events/write`
- **Request:** JSON body -- `model.Case` object. ID is generated server-side.
- **Response:**
  - `200` -- Created `model.Case` with generated ID
  - `400` -- Malformed input
  - `401` -- Not authenticated
  - `403` -- Insufficient permissions
  - `405` -- Case module not enabled
  - `500` -- Internal error
- **Business logic notes:** Delegates entirely to `Casestore.Create()`.
- **Async:** No

### POST /api/case/events
- **Summary:** Create Case Related Events (bulk attach)
- **RBAC:** `cases/read`, `cases/write`, `events/read`, `events/write`
- **Request:** JSON body -- `model.AttachEventCriteria` with `Fields`, `CaseId`, `DateRange`, `DateRangeFormat`, `Timezone`, `Acknowledged`, `Escalated` flags.
- **Response:**
  - `202` -- Accepted; returns `{ "count": N }` immediately
  - `400` -- Malformed input
  - `401` / `403` / `405` / `500`
- **Business logic notes:**
  - Builds an ES search query from the criteria fields.
  - Searches events via `Eventstore.Search()`, converts `EventRecord` to `RelatedEvent`.
  - Caps bulk events at `Config.ClientParams.AlertingParams.MaxBulkEscalateEvents`.
  - Fires `createEventsAsync()` in a goroutine that calls `Casestore.CreateRelatedEvents()`.
  - Broadcasts `"related:bulkCreate"` on `"cases"` channel when complete.
- **Async:** Yes -- returns 202 immediately; actual creation runs in background goroutine.

### POST /api/case/comments
- **Summary:** Create Case Comment
- **RBAC:** `cases/read`, `cases/write`, `events/read`, `events/write`
- **Request:** JSON body -- `model.Comment`. ID generated server-side.
- **Response:**
  - `200` -- Created `model.Comment` (note: swagger says `model.RelatedEvent` but code returns Comment)
  - `400` / `401` / `403` / `405` / `500`
- **Business logic notes:** Delegates to `Casestore.CreateComment()`.
- **Async:** No

### POST /api/case/tasks
### POST /api/case/artifacts
- **Summary:** Create Case Artifact (observable)
- **RBAC:** `cases/read`, `cases/write`, `events/read`, `events/write`
- **Request:**
  - JSON body -- `model.Artifact` for non-file artifacts.
  - Multipart form for file artifacts: `json` part (artifact JSON) + `attachment` part (file bytes). Max size: `Config.MaxUploadSizeBytes`.
- **Response:**
  - `200` -- Created `model.Artifact` with generated ID
  - `400` / `401` / `403` / `405` / `500`
- **Business logic notes:**
  - For file uploads: computes `StreamLen`, `MimeType`, `Md5`, `Sha1`, `Sha256` server-side.
  - `ArtifactType` forced to `"file"`; `Value` set to filename.
  - Creates artifact stream via `Casestore.CreateArtifactStream()` before creating the artifact.
  - Artifact value must be empty when uploading a file attachment.
- **Async:** No

### GET /api/case/
### GET /api/case/{id}
- **Summary:** Get Case
- **RBAC:** `cases/read`, `events/read`
- **Request:** Path param `id` or query param `id`.
- **Response:**
  - `200` -- `model.Case`
  - `400` / `401` / `403` / `404` / `405` / `500`
- **Business logic notes:** Delegates to `Casestore.GetCase()`.
- **Async:** No

### GET /api/case/comments
### GET /api/case/comments/{id}
- **Summary:** Get Case Comments
- **RBAC:** `cases/read`, `events/read`
- **Request:** Path param `id` or query param `id` (this is the case ID, not comment ID).
- **Response:**
  - `200` -- `[]model.Comment` (may be empty)
  - `400` / `401` / `403` / `405` / `500`
- **Business logic notes:** Delegates to `Casestore.GetComments()`.
- **Async:** No

### GET /api/case/events
### GET /api/case/events/{id}
- **Summary:** Get Related Events
- **RBAC:** `cases/read`, `events/read`
- **Request:** Path param `id` or query param `id` (case ID).
- **Response:**
  - `200` -- `[]model.RelatedEvent`
  - `400` / `401` / `403` / `405` / `500`
- **Business logic notes:** Delegates to `Casestore.GetRelatedEvents()`.
- **Async:** No

### GET /api/case/tasks
### GET /api/case/tasks/{id}
### GET /api/case/artifactstream
### GET /api/case/artifactstream/{id}
- **Summary:** Get Artifact Stream (download file artifact)
- **RBAC:** `cases/read`, `events/read`
- **Request:** Path param `id` or query param `id` (artifact's stream ID).
- **Response:**
  - `200` -- Binary stream with `Content-Disposition: attachment; filename="..."`, `Content-Transfer-Encoding: binary`.
  - If artifact is `Protected`, it is wrapped in a ZIP before sending.
  - `400` / `401` / `403` / `404` / `405` / `500`
- **Business logic notes:** Gets artifact metadata, then streams via `Casestore.GetArtifactStream()`. Protected artifacts are zipped in-memory.
- **Async:** No

### GET /api/case/artifacts/{groupType}
### GET /api/case/artifacts/{groupType}/{groupID}
### GET /api/case/artifacts/{groupType}/{groupID}/{id}
- **Summary:** Get Case Artifacts
- **RBAC:** `cases/read`, `events/read`
- **Request:** Path params `groupType` (e.g. `attachments`, `evidence`), optional `groupID`, optional `id`. Falls back to query param `id`.
- **Response:**
  - `200` -- `[]model.Artifact`
  - `400` / `401` / `403` / `405` / `500`
- **Business logic notes:** Delegates to `Casestore.GetArtifacts(ctx, id, groupType, groupId)`.
- **Async:** No

### GET /api/case/history
### GET /api/case/history/{id}
- **Summary:** Get Case History (audit trail)
- **RBAC:** `cases/read`, `events/read`
- **Request:** Path param `id` or query param `id` (case ID).
- **Response:**
  - `200` -- `[]model.Auditable`
  - `400` / `401` / `403` / `404` / `405` / `500`
- **Business logic notes:** Returns 404 on error (not 500).
- **Async:** No

### PUT /api/case/
- **Summary:** Update Case
- **RBAC:** `cases/read`, `cases/write`, `events/read`, `events/write`
- **Request:** JSON body -- `model.Case` with `Id` matching existing case.
- **Response:**
  - `200` -- Updated `model.Case`
  - `400` / `401` / `403` / `404` / `405` / `500`
- **Async:** No

### PUT /api/case/comments
- **Summary:** Update Case Comment
- **RBAC:** `cases/read`, `cases/write`, `events/read`, `events/write`
- **Request:** JSON body -- `model.Comment` with ID matching existing comment.
- **Response:**
  - `200` -- Updated `model.Comment`
  - `400` / `401` / `403` / `404` / `405` / `500`
- **Async:** No

### PUT /api/case/tasks
### PUT /api/case/artifacts
- **Summary:** Update Case Artifact
- **RBAC:** `cases/read`, `cases/write`, `events/read`, `events/write`
- **Request:** JSON body -- `model.Artifact`. Value and type cannot be modified.
- **Response:**
  - `200` -- Updated `model.Artifact`
  - `400` / `401` / `403` / `404` / `405` / `500`
- **Async:** No

### DELETE /api/case/comments
### DELETE /api/case/comments/{id}
- **Summary:** Delete Case Comment
- **RBAC:** `cases/read`, `cases/write`, `events/read`, `events/write`
- **Request:** Path param `id` or query param `id` (comment ID).
- **Response:** `200` / `400` / `401` / `403` / `404` / `405` / `500`
- **Async:** No

### DELETE /api/case/events
### DELETE /api/case/events/{id}
- **Summary:** Delete Case Related Event
- **RBAC:** `cases/read`, `cases/write`, `events/read`, `events/write`
- **Request:** Path param `id` or query param `id` (related event ID).
- **Response:** `200` / `400` / `401` / `403` / `404` / `405` / `500`
- **Async:** No

### DELETE /api/case/tasks
### DELETE /api/case/tasks/{id}
### DELETE /api/case/artifacts
### DELETE /api/case/artifacts/{id}
- **Summary:** Delete Case Artifact
- **RBAC:** `cases/read`, `cases/write`, `events/read`, `events/write`
- **Request:** Path param `id` or query param `id` (artifact ID).
- **Response:** `200` / `400` / `401` / `403` / `404` / `405` / `500`
- **Async:** No

---

## 2. EventHandler (`/api/events`)

**Source:** `server/eventhandler.go`
**Middleware:** `eventsEnabled` -- returns 405 if `Eventstore` is nil.

### GET /api/events/
- **Summary:** Query Data (search events)
- **RBAC:** `events/read`
- **Request:** Query params:
  - `query` (string, required) -- search query string
  - `range` (string, required) -- date range in specified timezone
  - `format` (string, required) -- date format string (e.g. `2006/01/02 3:04:05 PM`)
  - `zone` (string, required) -- timezone name
  - `metricLimit` (integer, required) -- max metrics per aggregation
  - `eventLimit` (integer, required) -- max events to return
- **Response:**
  - `200` -- `model.EventSearchResults`
  - `400` / `401` / `405` / `500`
- **Business logic notes:** Populates `EventSearchCriteria` from query params, delegates to `Eventstore.Search()`.
- **Async:** No

### POST /api/events/ack
- **Summary:** Acknowledge Alerts
- **RBAC:** `events/ack`, `events/write`
- **Request:** JSON body -- `model.EventAckCriteria`
- **Response:**
  - `200` -- `model.EventUpdateResults`
  - `400` / `401` / `405` / `500`
- **Business logic notes:** Delegates to `Eventstore.Acknowledge()`. Does not live-update other users' alert screens; they must refresh.
- **Async:** No

---

## 3. InfoHandler (`/api/info`)

**Source:** `server/infohandler.go`

### GET /api/info/
- **Summary:** Get Server Information
- **RBAC:** Any authenticated user (bearer token required, no specific permission)
- **Request:** No params.
- **Response:**
  - `200` -- `model.Info` containing: `Version`, `License`, `LicenseKey`, `LicenseStatus`, `Parameters` (client params, nil for API clients), `ElasticVersion`, `UserId`, `Timezones`, `SrvToken`, `ForceUserOtp`, `MgmtMac`, `Subgrids`, `CustomReports`
  - `401` / `500`
- **Business logic notes:**
  - Generates a `SrvToken` for CSRF protection (only for non-exempt/non-API requests).
  - Checks if user needs TOTP setup (`ForceUserOtp`).
  - Looks up management MAC address from nodes.
  - Validates subgrid count against license.
  - Reads custom report `.md` files from `Config.CustomReportsPath`.
- **Async:** No

---

## 4. JobHandler (`/api/job`)

**Source:** `server/jobhandler.go`

### GET /api/job/
### GET /api/job/{jobId}
- **Summary:** Get Job
- **RBAC:** `jobs/read`
- **Request:** Path param `jobId` (integer) or query param `jobId`.
- **Response:**
  - `200` -- `model.Job`
  - `400` -- Invalid job ID format
  - `401` / `404` / `500`
- **Business logic notes:** Delegates to `Datastore.GetJob()`.
- **Async:** No

### POST /api/job/
- **Summary:** Create Job
- **RBAC:** `jobs/write`
- **Request:** JSON body -- `model.Job`. Only `kind`, `nodeId`, and `parameters` typically needed. ID, timestamps, and status set server-side.
- **Response:**
  - `201` -- Created `model.Job`
  - `400` / `401` / `500`
- **Business logic notes:** Creates via `Datastore.CreateJob()` + `Datastore.AddJob()`. Broadcasts `"job"` on `"jobs"` channel.
- **Async:** No

### PUT /api/job/
- **Summary:** Update Job
- **RBAC:** `jobs/write`
- **Request:** JSON body -- `model.Job`. User ID and node ID are read-only after creation.
- **Response:**
  - `200` -- Updated `model.Job`
  - `400` / `401` / `404` / `500`
- **Business logic notes:** Delegates to `Datastore.UpdateJob()`. Broadcasts `"job"` on `"jobs"`.
- **Async:** No

### DELETE /api/job/{jobId}
- **Summary:** Delete Job
- **RBAC:** `jobs/delete`
- **Request:** Path param `jobId` (integer).
- **Response:**
  - `200` -- Job deleted
  - `400` / `401` / `404` / `500`
- **Business logic notes:** Delegates to `Datastore.DeleteJob()`. Broadcasts `"job"` on `"jobs"`.
- **Async:** No

---

## 5. JobsHandler (`/api/jobs`)

**Source:** `server/jobshandler.go`

### GET /api/jobs/
- **Summary:** Get Jobs (list/search)
- **RBAC:** `jobs/read`
- **Request:** Query params:
  - `kind` (string, required) -- job kind (e.g. `analyze`, or empty for PCAP jobs)
  - `parameters` (string, optional) -- JSON-encoded parameter filters (e.g. `{"artifact":{"id":"..."}}`)
- **Response:**
  - `200` -- `[]model.Job`
  - `400` / `401` / `500`
- **Business logic notes:** Delegates to `Datastore.GetJobs()`.
- **Async:** No

---

## 6. PacketHandler (`/api/packets`)

**Source:** `server/packethandler.go`

### GET /api/packets/
### GET /api/packets/{jobId}
- **Summary:** Get PCAP Packets
- **RBAC:** `jobs/read`
- **Request:** Path param `jobId` (integer) or query param `jobId`. Query params:
  - `unwrap` (bool, optional, default false) -- unwrap VXLAN etc.
  - `offset` (integer, optional, default 0) -- starting packet offset for paging
  - `count` (integer, optional, default `Config.MaxPacketCount`) -- max packets to retrieve
- **Response:**
  - `200` -- `[]model.Packet`
  - `400` / `401` / `404` / `500`
- **Business logic notes:** Count is clamped to server-side max. Delegates to `Datastore.GetPackets()`.
- **Async:** No

---

## 7. QueryHandler (`/api/query`)

**Source:** `server/queryhandler.go`

### GET /api/query/{operation}
- **Summary:** Build Query (modify a query string)
- **RBAC:** Any authenticated user (bearer token only)
- **Request:** Path param `operation` (one of: `filtered`, `grouped`, `sorted`). Form params:
  - `query` (string) -- current query to modify
  - `field` (string) -- field for the operation
  - `scalar` (bool) -- whether field is scalar (for filtered)
  - `mode` (string) -- operation mode (for filtered)
  - `value` / `value[]` (string/strings) -- filter value(s) (for filtered)
  - `group` (integer) -- group index (for grouped)
- **Response:**
  - `200` -- Plain text altered query string
  - `400` / `401` / `500`
- **Business logic notes:**
  - `filtered`: Calls `query.Filter()` for each value. Supports multi-value via `value[]`.
  - `grouped`: Calls `query.Group()` at the given index.
  - `sorted`: Calls `query.Sort()`.
- **Async:** No

### GET /api/query/active
- **Summary:** Get Active Queries
- **RBAC:** `queries/read`
- **Request:** Query param `filter` (bool, optional) -- if true, filters out internal/child/uncancelable queries.
- **Response:**
  - `200` -- `[]model.QueryTask`
  - `400` -- License invalid (requires Pro license `FEAT_QRY`)
  - `401` / `403` / `500`
- **Business logic notes:** Requires `licensing.FEAT_QRY`. Users see only their own queries unless privileged.
- **Async:** No

### POST /api/query/cancel/{queryId}
- **Summary:** Cancel Active Query
- **RBAC:** `queries/delete`
- **Request:** Path param `queryId` (string).
- **Response:**
  - `200` -- Cancellation submitted
  - `400` -- License invalid or query cannot be canceled
  - `401` / `403` / `404` -- Query not found
  - `500`
- **Business logic notes:** Requires `licensing.FEAT_QRY`. Not all queries are cancelable.
- **Async:** No

---

## 8. NodeHandler (`/api/node`)

**Source:** `server/nodehandler.go`

### POST /api/node/
- **Summary:** Node Check-in (agent heartbeat)
- **RBAC:** `nodes/write`, `jobs/process`
- **Request:** JSON body -- `model.Node` with recent metrics.
- **Response:**
  - `200` -- `model.Job` (next pending job for this node, or null)
  - `400` / `401` / `500`
- **Business logic notes:**
  - Updates node via `Datastore.UpdateNode()`.
  - Pushes metrics via `Metrics.UpdateNodeMetrics()`.
  - Broadcasts `"node"` on `"nodes"` channel.
  - Returns next job via `Datastore.GetNextJob()`.
- **Async:** No

---

## 9. GridHandler (`/api/grid`)

**Source:** `server/gridhandler.go`

### GET /api/grid/
- **Summary:** Get Grid Nodes
- **RBAC:** `nodes/read`
- **Request:** Query param `assignedGridId` (optional) -- injected into each node's response.
- **Response:**
  - `200` -- `[]model.Node`
  - `401` / `403` / `500`
- **Business logic notes:** Gets nodes from `Datastore.GetNodes()`. Copies each node to inject `GridId`.
- **Async:** No

### GET /api/grid/status
- **Summary:** Get Grid Status
- **RBAC:** `grid/read`
- **Request:** Query param `assignedGridId` (optional).
- **Response:**
  - `200` -- `model.Status` (grid health including nodes, alerts, detection engines)
  - `401` / `403` / `500`
- **Business logic notes:** Delegates to `Statusstore.GetStatusSummary()`. Injects `GridId` into response copy.
- **Async:** No

---

## 10. StreamHandler (`/api/stream`)

**Source:** `server/streamhandler.go`

### GET /api/stream/
### GET /api/stream/{jobId}
- **Summary:** Download Job Output (e.g. PCAP file)
- **RBAC:** `jobs/read`
- **Request:** Path param `jobId` (integer) or query param `jobId`. Query params:
  - `ext` (string, optional) -- filename extension to append (validated: `[a-zA-Z0-9]+`)
  - `unwrap` (bool, optional, default false) -- unwrap VXLAN etc.
- **Response:**
  - `200` -- Binary stream with headers: `Content-Type` (MIME), `Content-Length`, `Content-Disposition: inline; filename="..."`, `Content-Transfer-Encoding: binary`
  - `400` / `401` / `403` / `404` / `500`
- **Business logic notes:** Calls `Datastore.GetJobStream()`. Replaces `.bin` extension if custom ext provided.
- **Async:** No

### POST /api/stream/
### POST /api/stream/{jobId}
- **Summary:** Upload Job Output
- **RBAC:** `jobs/process`
- **Request:** Path param `jobId` (integer) or query param `jobId`. Body: raw `application/octet-stream` bytes.
- **Response:**
  - `200` -- Saved
  - `400` / `401` / `403` / `404` / `500`
- **Business logic notes:** Delegates to `Datastore.SaveJobStream()`.
- **Async:** No

---

## 11. UsersHandler (`/api/users`)

**Source:** `server/usershandler.go`
**Middleware:** `usersEnabled` -- returns 405 if `Userstore` is nil (or 200 in developer mode).
**Validation:** User IDs validated with regex `^[A-Za-z0-9-]{36}$`. Roles validated with `^[A-Za-z0-9-_]{3,50}$`.

### GET /api/users/
- **Summary:** Get Users
- **RBAC:** `users/read`
- **Response:**
  - `200` -- `[]model.User`
  - `401` / `405` / `500`
- **Business logic notes:** Calls `Rolestore.EnsureDefaultRoleForUser()` before fetching users.
- **Async:** No

### POST /api/users/
- **Summary:** Create User
- **RBAC:** `users/write`
- **Request:** JSON body -- `model.User` (email, firstname, lastname, note, roles, password used; other fields ignored).
- **Response:**
  - `200` -- `model.User`
  - `400` / `401` / `405` / `500`
- **Business logic notes:** Calls `user.Verify()` then `AdminUserstore.AddUser()`.
- **Async:** No

### POST /api/users/{id}/role/{role}
- **Summary:** Grant User Role
- **RBAC:** `users/write`
- **Request:** Path params `id` (UUID), `role` (string).
- **Response:** `200` / `400` / `401` / `405` / `500`
- **Business logic notes:** Calls `AdminUserstore.AddRole(ctx, id, role, false)`.
- **Async:** No

### PUT /api/users/sync
- **Summary:** Synchronize Users
- **RBAC:** `users/write`
- **Response:** `200` / `401` / `405` / `500`
- **Business logic notes:** Calls `AdminUserstore.SyncUsers()`. Async background operation.
- **Async:** Yes (background sync)

### PUT /api/users/{id}
- **Summary:** Update User
- **RBAC:** `users/write`
- **Request:** Path param `id`. JSON body -- `model.User` (email, firstname, lastname, note updated; other fields ignored).
- **Response:**
  - `200` -- `model.User`
  - `400` / `401` / `405` / `500`
- **Business logic notes:** Sets `user.Id = id` from path, calls `user.Verify()`, then `AdminUserstore.UpdateProfile()`.
- **Async:** No

### PUT /api/users/{id}/password
- **Summary:** Change Password
- **RBAC:** `users/write`
- **Request:** Path param `id` (UUID validated). JSON body -- `model.User` with `Password` field.
- **Response:** `200` / `400` / `401` / `405` / `500`
- **Business logic notes:** Validates ID format, then `AdminUserstore.ResetPassword()`.
- **Async:** No

### PUT /api/users/{id}/{toggle}
- **Summary:** Toggle User Enabled/Disabled
- **RBAC:** `users/write`
- **Request:** Path params `id` (UUID validated), `toggle` (`enable` or `disable`).
- **Response:** `200` / `400` / `401` / `405` / `500`
- **Business logic notes:** Calls `AdminUserstore.EnableUser()` or `AdminUserstore.DisableUser()`.
- **Async:** No

### DELETE /api/users/{id}
- **Summary:** Delete User
- **RBAC:** `users/write`
- **Request:** Path param `id` (UUID validated).
- **Response:** `200` / `400` / `401` / `405` / `500`
- **Business logic notes:** Calls `AdminUserstore.DeleteUser()`.
- **Async:** No

### DELETE /api/users/{id}/role/{role}
- **Summary:** Deny User Role
- **RBAC:** `users/write`
- **Request:** Path params `id` (UUID validated), `role` (validated).
- **Response:** `200` / `400` / `401` / `405` / `500`
- **Business logic notes:** Calls `AdminUserstore.DeleteRole()`.
- **Async:** No

---

## 12. ClientsHandler (`/api/clients`)

**Source:** `server/clientshandler.go`
**License gate:** All endpoints check `licensing.IsEnabled(licensing.FEAT_API)` and return 400 with `"ERROR_LICENSE_INVALID"` if not licensed.
**Validation:** Client IDs validated with `^[A-Za-z0-9_]{6,55}$`. Permissions validated with `^[a-z]+/[a-z_]+$`.

### GET /api/clients/
- **Summary:** Get API Clients
- **RBAC:** `clients/read`
- **Response:**
  - `200` -- `[]model.Client`
  - `400` (license) / `401` / `403` / `500`
- **Business logic notes:** Delegates to `Clientstore.GetClients()`.
- **Async:** No

### POST /api/clients/
- **Summary:** Create API Client
- **RBAC:** `clients/write`
- **Request:** JSON body -- `model.Client` (only `name` and `note` used).
- **Response:**
  - `200` -- `model.Client` with assigned ID and secret
  - `400` (license / validation) / `401` / `403` / `500`
- **Business logic notes:** Calls `client.Verify()`, then `AdminClientstore.AddClient()`.
- **Async:** No

### POST /api/clients/{id}/permission/{resource}/{privilege}
- **Summary:** Assign Client Permission
- **RBAC:** `clients/write`
- **Request:** Path params `id`, `resource`, `privilege`. Permission = `resource/privilege`.
- **Response:** `200` / `400` (license / invalid) / `401` / `403` / `500`
- **Business logic notes:** Validates ID and permission format. Calls `AdminClientstore.AddClientPermission()`. Takes effect immediately without new access token.
- **Async:** No

### PUT /api/clients/{id}
- **Summary:** Update API Client
- **RBAC:** `clients/write`
- **Request:** Path param `id`. JSON body -- `model.Client` (name, note).
- **Response:**
  - `200` -- `model.Client`
  - `400` (license / invalid) / `401` / `403` / `500`
- **Business logic notes:** Sets `client.Id` from path, validates, then `AdminClientstore.UpdateClient()`.
- **Async:** No

### PUT /api/clients/{id}/secret
- **Summary:** Regenerate Client Secret
- **RBAC:** `clients/write`
- **Request:** Path param `id` (validated).
- **Response:**
  - `200` -- `model.Client` with new secret
  - `400` (license / invalid) / `401` / `403` / `500`
- **Business logic notes:** Existing access tokens remain valid until expiration. New secret generated via `AdminClientstore.GenerateSecret()`.
- **Async:** No

### DELETE /api/clients/{id}
- **Summary:** Remove API Client
- **RBAC:** `clients/write`
- **Request:** Path param `id` (validated).
- **Response:** `200` / `400` (license / invalid) / `401` / `403` / `500`
- **Business logic notes:** Calls `AdminClientstore.DeleteClient()`. Future requests rejected immediately.
- **Async:** No

### DELETE /api/clients/{id}/permission/{resource}/{privilege}
- **Summary:** Remove Client Permission
- **RBAC:** `clients/write`
- **Request:** Path params `id`, `resource`, `privilege`.
- **Response:** `200` / `400` (license / invalid) / `401` / `403` / `500`
- **Business logic notes:** Takes effect immediately.
- **Async:** No

---

## 13. ConfigHandler (`/api/config`)

**Source:** `server/confighandler.go`
**Middleware:** `configEnabled` -- returns 405 if `Configstore` is nil.

### GET /api/config/
- **Summary:** Get Configuration
- **RBAC:** `config/read`
- **Request:** Query param `advanced` (bool, optional, default false) -- if true returns all settings.
- **Response:**
  - `200` -- `[]model.Setting`
  - `401` / `403` / `405` / `500`
- **Business logic notes:** Delegates to `Configstore.GetSettings(ctx, advanced)`.
- **Async:** No

### PUT /api/config/
### POST /api/config/
- **Summary:** Save Setting
- **RBAC:** `config/read`, `config/write`
- **Request:** JSON body -- `model.Setting` (requires `id` and `value`, optional `nodeId` for node-specific settings).
- **Response:** `200` / `400` / `401` / `403` / `405` / `500`
- **Business logic notes:**
  - Validates `setting.Id` with `model.IsValidSettingId()`.
  - Validates `setting.NodeId` with `model.IsValidMinionId()` if present.
  - Calls `Configstore.UpdateSetting(ctx, &setting, false)`.
- **Async:** No

### PUT /api/config/sync
### POST /api/config/sync
- **Summary:** Sync Configuration (grid-wide)
- **RBAC:** `config/write`
- **Response:** `200` / `401` / `403` / `405` / `500`
- **Business logic notes:** Queues a Salt highstate. Can take several minutes. Calls `Configstore.SyncSettings()`.
- **Async:** No (queues but returns immediately)

### PUT /api/config/sync/{module}
- **Summary:** Sync Specific Module Configuration
- **RBAC:** `config/write`
- **Request:** Path param `module` (string). Query param `async` (string, optional) -- `"true"` to run in background.
- **Response:** `200` / `401` / `403` / `405` / `500`
- **Business logic notes:** Calls `Configstore.SyncModule(ctx, module, async)`. If async=false and another state is running, returns error.
- **Async:** Configurable via `async` query param

### DELETE /api/config/
### DELETE /api/config/{id}
### DELETE /api/config/{id}/{minion}
- **Summary:** Delete Setting (revert to default)
- **RBAC:** `config/read`, `config/write`
- **Request:** Path params `id`, optional `minion`. Falls back to query params `id`, `minion`.
- **Response:** `200` / `400` / `401` / `403` / `405` / `500`
- **Business logic notes:** Validates setting ID and minion ID. Calls `Configstore.UpdateSetting(ctx, setting, true)` (delete mode).
- **Async:** No

---

## 14. GridMembersHandler (`/api/gridmembers`)

**Source:** `server/gridmembershandler.go`
**Middleware:** `gridMembersEnabled` -- returns 405 if `GridMembersstore` is nil.
**Validation:** Minion IDs validated with `model.IsValidMinionId()`.

### GET /api/gridmembers/
- **Summary:** Get Grid Members
- **RBAC:** `grid/read`
- **Response:**
  - `200` -- `[]model.GridMember`
  - `401` / `403` / `405` / `500`
- **Business logic notes:** Returns all members including pending, accepted, and rejected.
- **Async:** No

### POST /api/gridmembers/{id}/import
- **Summary:** Import Data (PCAP or EVTX)
- **RBAC:** `events/write`
- **Request:** Path param `id` (node ID, e.g. `manager_standalone`). Multipart form with `attachment` file.
- **Response:**
  - `202` -- Upload accepted, import started
  - `400` -- Invalid file, extension, magic bytes, or node doesn't support file type
  - `401` / `403` / `405` / `409` (file already exists) / `500`
- **Business logic notes:**
  - Validates file extension (`.pcap` or `.evtx` only).
  - Validates magic bytes for each file type.
  - Checks node role supports the file type (`canUploadPcap` / `canUploadEvtx`).
  - Upload limit: `Config.ClientParams.GridParams.MaxUploadSize` (default 25 MiB).
  - Writes file to `Config.ImportUploadDir` then sends to node via `GridMembersstore.SendFile()`.
  - Imports via `GridMembersstore.Import()` in a goroutine.
  - Broadcasts `"import"` on `"jobs"` channel with dashboard URL or `"no-changes"`.
- **Async:** Yes -- returns 202 immediately, import runs in goroutine.

### POST /api/gridmembers/{id}/{operation}
- **Summary:** Manage Grid Member
- **RBAC:** `grid/write`
- **Request:** Path params `id` (minion ID), `operation` (one of: `add`, `reject`, `delete`, `test`, `restart`).
- **Response:** `200` / `400` / `401` / `403` / `405` / `500`
- **Business logic notes:** Delegates to `GridMembersstore.ManageMember(ctx, op, id)`.
- **Async:** No

---

## 15. RolesHandler (`/api/roles`)

**Source:** `server/roleshandler.go`
**Middleware:** `rolesEnabled` -- returns 405 if `Rolestore` is nil.

### GET /api/roles/
- **Summary:** Get Roles
- **RBAC:** `roles/read`
- **Response:**
  - `200` -- `[]string` (role names)
  - `401` / `405` / `500`
- **Async:** No

### GET /api/roles/permissions
- **Summary:** Get Permissions
- **RBAC:** `permissions/read`
- **Response:**
  - `200` -- `[]string` (permission names)
  - `401` / `405` / `500`
- **Business logic notes:** Returns permissions that can be assigned to API clients (not user roles).
- **Async:** No

---

## 16. DetectionHandler (`/api/detection`)

**Source:** `server/detectionhandler.go`
**Note:** This is the largest handler group. Many operations involve syncing detection rules to engine-specific files after changes.

### GET /api/detection/{id}
- **Summary:** Get Detection (by internal ID)
- **RBAC:** `detections/read`, `events/read`
- **Request:** Path param `id` (internal detection ID).
- **Response:**
  - `200` -- `model.Detection` (with merged auxiliary data from engine)
  - `401` / `403` / `404` / `500`
- **Business logic notes:** Loads detection, then merges auxiliary data from the detection engine.
- **Async:** No

### GET /api/detection/public/{publicid}
- **Summary:** Get Detection by Public ID
- **RBAC:** `detections/read`, `events/read`
- **Request:** Path param `publicid` (assigned by ruleset author).
- **Response:**
  - `200` -- `model.Detection`
  - `401` / `403` / `404` / `500`
- **Business logic notes:** Same as above but by public ID. Merges auxiliary data.
- **Async:** No

### POST /api/detection/
- **Summary:** Create Detection
- **RBAC:** `detections/read`, `events/read`, `detections/write`, `events/write`, `users/read`
- **Request:** JSON body -- `model.Detection`
- **Response:**
  - `200` -- Created `model.Detection`
  - `205` -- Created but status was modified by an engine filter
  - `400` -- Invalid rule, missing public ID, community detection, or unsupported engine
  - `401` / `403` / `409` (public ID conflict) / `423` (sync blocked) / `500`
- **Business logic notes:**
  - Cannot create community detections via this endpoint.
  - Language determines engine: `sigma` -> `ElastAlert`, `yara` -> `Strelka`, `suricata` -> `Suricata`.
  - Ruleset forced to `RULESET_CUSTOM`.
  - Validates rule via engine, extracts details, sets author from authenticated user.
  - Applies engine filters (may change `IsEnabled` status).
  - After creation, triggers `syncLocalDetections()` to regenerate rule files.
  - Returns 205 if a filter changed the status from what the user submitted.
- **Async:** No (sync is synchronous)

### POST /api/detection/{id}/duplicate
- **Summary:** Duplicate Detection
- **RBAC:** `detections/read`, `events/read`, `detections/write`, `events/write`
- **Request:** Path param `id`.
- **Response:**
  - `200` -- Duplicated `model.Detection` with new ID
  - `400` -- Unsupported engine
  - `401` / `403` / `500`
- **Business logic notes:** Delegates to engine's `DuplicateDetection()`, then `Detectionstore.CreateDetection()`.
- **Async:** No

### POST /api/detection/{id}/comment
- **Summary:** Create Detection Comment
- **RBAC:** `detections/read`, `events/read`, `detections/write`, `events/write`
- **Request:** Path param `id` (detection ID). JSON body -- `model.DetectionComment`.
- **Response:**
  - `200` -- `model.DetectionComment`
  - `400` / `401` / `403` / `500`
- **Business logic notes:** Forces `DetectionId` from path param. Delegates to `Detectionstore.CreateComment()`.
- **Async:** No

### GET /api/detection/comment/{id}
- **Summary:** Get Detection Comment
- **RBAC:** `detections/read`, `events/read`
- **Request:** Path param `id` (comment ID).
- **Response:**
  - `200` -- `model.DetectionComment`
  - `401` / `403` / `404` / `500`
- **Async:** No

### PUT /api/detection/comment/{id}
- **Summary:** Update Detection Comment
- **RBAC:** `detections/read`, `events/read`, `detections/write`, `events/write`
- **Request:** Path param `id` (comment ID). JSON body -- `model.DetectionComment`.
- **Response:**
  - `200` -- Updated `model.DetectionComment`
  - `400` / `401` / `403` / `404` / `500`
- **Business logic notes:** Forces `Id` from path param.
- **Async:** No

### DELETE /api/detection/comment/{id}
- **Summary:** Delete Detection Comment
- **RBAC:** `detections/read`, `events/read`, `detections/write`, `events/write`
- **Request:** Path param `id` (comment ID).
- **Response:** `200` / `401` / `403` / `404` / `500`
- **Async:** No

### GET /api/detection/{id}/comment
- **Summary:** Get Detection Comments (all for a detection)
- **RBAC:** `detections/read`, `events/read`
- **Request:** Path param `id` (detection ID).
- **Response:**
  - `200` -- `[]model.DetectionComment`
  - `401` / `403` / `404` / `500`
- **Async:** No

### GET /api/detection/{id}/history
- **Summary:** Get Detection History (audit trail)
- **RBAC:** `detections/read`, `events/read`
- **Request:** Path param `id` or query param `id` (internal detection ID).
- **Response:**
  - `200` -- `[]model.Auditable`
  - `401` / `403` / `404` / `500`
- **Async:** No

### POST /api/detection/convert
- **Summary:** Convert Rule Query (Sigma to ES query)
- **RBAC:** Any authenticated user (bearer)
- **Request:** JSON body -- `model.Detection` with `Content` and optional `Overrides`.
- **Response:**
  - `200` -- `{ "query": "..." }`
  - `400` -- Not a Sigma/ElastAlert detection
  - `401` / `403` / `500`
- **Business logic notes:** Only works with Sigma rules / ElastAlert engine. Calls `engine.ConvertRule()`.
- **Async:** No

### PUT /api/detection/
- **Summary:** Update Detection
- **RBAC:** `detections/read`, `events/read`, `detections/write`, `events/write`
- **Request:** JSON body -- `model.Detection`
- **Response:**
  - `200` -- Updated `model.Detection`
  - `205` -- Updated but status modified by engine filter
  - `206` -- Updated but detection was disabled to complete sync (sync error recovery)
  - `400` / `401` / `403` / `404` / `409` (public ID conflict) / `423` (sync blocked) / `500`
- **Business logic notes:**
  - Validates rule, applies filters, preserves Author/License/CreateTime/Ruleset from original.
  - Community rules: only `IsEnabled`, `IsReporting`, `Overrides`, and `Tags` are editable.
  - Cannot convert non-community to community.
  - Override timestamps managed: new overrides get current time, unchanged overrides preserve timestamps.
  - On sync failure for enabled non-filtered detections: auto-disables and re-syncs.
  - Merges auxiliary data after update.
- **Async:** No

### PUT /api/detection/{id}/override/{overrideIndex}/note
- **Summary:** Update Override Note
- **RBAC:** `detections/read`, `events/read`, `detections/write`, `events/write`
- **Request:** Path params `id`, `overrideIndex` (0-based integer). JSON body -- `model.OverrideNoteUpdate`.
- **Response:** `200` / `400` / `401` / `403` / `500`
- **Async:** No

### DELETE /api/detection/{id}
- **Summary:** Delete Detection
- **RBAC:** `detections/read`, `events/read`, `detections/write`, `events/write`
- **Request:** Path param `id`.
- **Response:**
  - `200` -- Error map from sync (may be empty `{}`)
  - `400` -- Cannot delete community detections (`ERROR_DELETE_COMMUNITY`)
  - `401` / `403` / `404` / `423` (sync blocked) / `500`
- **Business logic notes:** Deletes from store, then syncs with `IsEnabled=false`, `PendingDelete=true`. Returns `403` for unauthorized delete attempts.
- **Async:** No

### POST /api/detection/bulk/{newStatus}
- **Summary:** Manage Detections in Bulk (enable/disable/delete)
- **RBAC:** `detections/read`, `events/read`, `detections/write`, `events/write` (explicit `detections/write` check in handler)
- **Request:** Path param `newStatus` (`enable`, `disable`, or `delete`). JSON body -- `BulkOp`:
  - `ids` ([]string) -- detection IDs (used if `query` is nil)
  - `query` (*string) -- query string to match detections (overrides `ids`)
- **Response:**
  - `202` -- `{ "count": N }` -- bulk operation started
  - `400` -- Invalid status, or `ERROR_BULK_COMMUNITY` (cannot delete community detections)
  - `401` / `403` / `500`
- **Business logic notes:**
  - Uses ES bulk indexer for efficiency.
  - Applies engine filters to each detection (may prevent status change).
  - Creates audit records for each successful update.
  - Syncs all dirty detections after bulk update.
  - Broadcasts `"detections:bulkUpdate"` on `"detections"` channel.
  - Community detections cannot be deleted in bulk (can be enabled/disabled).
- **Async:** Yes -- returns 202, runs `bulkUpdateDetectionAsync()` in goroutine.

### POST /api/detection/sync/{engine}/{type}
- **Summary:** Sync Detections for Engine
- **RBAC:** `detections/write` (explicit check)
- **Request:** Path params:
  - `engine` (string) -- `all`, `elastalert`, `suricata`, `strelka`
  - `type` (string) -- `full` or `update`
- **Response:** `200` / `400` (unknown engine) / `401` / `403` / `500`
- **Business logic notes:** Calls `engine.InterruptSync(fullUpgrade, true)` for one or all engines.
- **Async:** No (queues sync but returns immediately)

### GET /api/detection/{engine}/genpublicid
- **Summary:** Generate Public ID
- **RBAC:** Any authenticated user (bearer)
- **Request:** Path param `engine` (e.g. `elastalert`, `suricata`).
- **Response:**
  - `200` -- `{ "publicId": "..." }`
  - `400` -- Unsupported engine
  - `401` / `403` / `500` / `501` -- Engine doesn't support public IDs
- **Async:** No

---

## 17. PlaybookHandler (`/api/playbook`)

**Source:** `server/playbookhandler.go`

### GET /api/playbook/{id}
- **Summary:** Get Playbook by ID
- **RBAC:** `playbooks/read` (explicit check in handler)
- **Request:** Path param `id` (playbook ID).
- **Response:**
  - `200` -- `model.Playbook`
  - `400` -- Missing ID
  - `401` / `404` / `500`
- **Async:** No

### GET /api/playbook/detection/{id}
- **Summary:** Get Playbooks For Detection
- **RBAC:** `playbooks/read`, `detections/read`, `events/read` (all three checked explicitly)
- **Request:** Path param `id` (detection public ID). Query param `raw` (bool, optional) -- return YAML instead of JSON.
- **Response:**
  - `200` -- `[]model.Playbook` (JSON) or `application/x-yaml` (raw, `---` separated)
  - `400` -- Missing ID
  - `401` / `404` / `500`
- **Business logic notes:** Looks up detection by public ID, extracts details via engine, then finds matching playbooks by `PublicID`, `Category`, and `Engine`.
- **Async:** No

### GET /api/playbook/event/{id}
- **Summary:** Get Event-Specific Playbook
- **RBAC:** `playbooks/read`, `detections/read`, `events/read` (all three checked explicitly)
- **Request:** Path param `id` (SOC alert ID).
- **Response:**
  - `200` -- `[]model.Playbook`
  - `400` -- Missing ID
  - `401` / `404` (no alert found) / `500`
- **Async:** No

---

## 18. AssistantHandler (`/api/assistant`)

**Source:** `server/assistanthandler.go`
**Availability check:** All endpoints (except admin) check `Config.AirgapEnabled`; return 500 `"ERROR_SERVICE_NOT_AVAILABLE"` on airgapped installations.

### POST /api/assistant/chat
- **Summary:** Send Chat Message
- **RBAC:** `assistant/write_authored`
- **Request:** JSON body -- `{ "msg": string, "sessionId": string (optional), "tags": []string, "model": string }`. Query params:
  - `entityType` (string, optional) -- e.g. `alert_investigation`
  - `entityId` (string, optional) -- e.g. alert's `soc_id`
- **Request Header:** `Accept: text/event-stream` for streaming SSE; otherwise JSON.
- **Response:**
  - `200` -- `[]model.Message` (non-streaming) or SSE stream (streaming)
  - `400` -- Malformed input or `ERROR_ASSISTANT_REQUEST_TOO_LARGE`
  - `401` / `403` / `500` (`ERROR_UPSTREAM_SERVICE_ERROR`)
- **Business logic notes:**
  - Generates `sessionId` if not provided.
  - If `entityType=alert_investigation` and `entityId` provided: marks alert as investigated via `Eventstore.Update()`.
  - Retrieves chat history, appends new user message, sends to `AssistantManager.Chat()` or `ChatStream()`.
  - Creates new session on first message.
  - Saves all messages to `Assistantstore`.
  - Streaming: proxies raw SSE from upstream, then parses and saves response asynchronously in goroutine.
  - Context compression: on history replay, messages before a `MessageTagContextCompression` tag are dropped.
- **Async:** Partially -- streaming response saved asynchronously.

### POST /api/assistant/tool/{name}
- **Summary:** Execute Tool
- **RBAC:** `assistant/write_authored` (additional permissions may be checked depending on tool)
- **Request:** Path param `name` (tool name). JSON body -- `model.ToolRequest` with `sessionId`, `toolUseId`, `params`, `auxData`, `model`.
- **Request Header:** `Accept: text/event-stream` for streaming.
- **Response:**
  - `200` -- `[]model.Message` (non-streaming) or SSE stream
  - `400` / `401` / `403` / `500`
- **Business logic notes:**
  - Executes tool via `AssistantManager.ExecuteTool()`.
  - On tool error: creates error tool result with `isError: true`.
  - Sends tool result + history to `AssistantManager.Chat()` / `ChatStream()` for continuation.
  - Saves tool result message with `["tool_result"]` tags.
  - Streaming save runs in goroutine.
- **Async:** Partially -- streaming response saved asynchronously.

### GET /api/assistant/balance/*
- **Summary:** Get Assistant Balance
- **RBAC:** `assistant/read_authored` OR `assistant/read_all`
- **Request:** Wildcard path captures model and adapter name (e.g. `qwen/qwen2.5-small@MyOpenAIChatAdapter`).
- **Response:**
  - `200` -- `model.Usage` with `HealthStatus` field added
  - `401` / `403` / `500`
- **Business logic notes:** Calls both `AssistantManager.Health()` and `AssistantManager.Balance()`. Health status is merged into balance response.
- **Async:** No

### GET /api/assistant/sessions
- **Summary:** Get Assistant Sessions (for current user)
- **RBAC:** `assistant/read_authored`
- **Response:**
  - `200` -- `[]model.AssistantSession`
  - `401` / `403` / `500`
- **Business logic notes:** Filters by current user's ID.
- **Async:** No

### GET /api/assistant/sessions/{sessionId}
- **Summary:** Get Session Details (history + usage)
- **RBAC:** `assistant/read_authored` (or `assistant/read_shared`)
- **Request:** Path param `sessionId`.
- **Response:**
  - `200` -- `model.AssistantSessionDetails` (session metadata + chat history). Returns empty details if session not found.
  - `400` / `401` / `403` / `500`
- **Business logic notes:** Includes deleted sessions. Includes usage stats. Strips auxiliary data (thought signatures) from history.
- **Async:** No

### PUT /api/assistant/sessions/{sessionId}
- **Summary:** Update Session Metadata (tags)
- **RBAC:** `assistant/write_authored`
- **Request:** Path param `sessionId`. JSON body -- `model.UpdateSessionRequest` with `action` (`add` or `remove`) and `tag`.
- **Response:**
  - `204` -- No content (success)
  - `400` -- Missing session ID
  - `401` / `403` / `404` -- Session not found
  - `409` -- Tag already exists (add) or tag cannot be removed (attached to cases)
  - `500`
- **Business logic notes:**
  - `add`: Appends tag if not already present.
  - `remove`: Validates tag can be removed (checks if session is attached to cases via `Casestore.GetCaseIdsWithArtifact()`). Rejects removal if attached to cases with error `"ERROR_SESSION_ATTACHED_TO_CASES N"`.
- **Async:** No

### DELETE /api/assistant/sessions/{sessionId}
- **Summary:** Delete Session
- **RBAC:** `assistant/delete_authored`
- **Request:** Path param `sessionId`.
- **Response:**
  - `204` -- Deleted
  - `400` / `401` / `403` / `500`
- **Business logic notes:**
  - Before deletion: if session is type `alert_investigation` with an `entityId`, clears the `investigation_session_id` from the associated alert via `Eventstore.Update()`.
  - Delegates to `Assistantstore.DeleteSession()`.
- **Async:** No

### GET /api/assistant/admin/stats
- **Summary:** Get Usage Statistics (all users)
- **RBAC:** `assistant/read_all`
- **Request:** Query params:
  - `range` (string, required) -- date range
  - `format` (string, required) -- date format
  - `zone` (string, required) -- timezone
- **Response:**
  - `200` -- `[]model.UserUsage`
  - `400` / `401` / `403` / `500`
- **Async:** No

### GET /api/assistant/admin/sessions
- **Summary:** Get All Sessions (all users)
- **RBAC:** `assistant/read_all`
- **Request:** Same query params as admin sessions below.
- **Response:**
  - `200` -- `[]model.AssistantSession`
  - `400` / `401` / `403` / `500`
- **Business logic notes:** Delegates to `GetSessionsAdmin` without a userId filter.
- **Async:** No

### GET /api/assistant/admin/{userId}/sessions
- **Summary:** Get User Sessions (admin)
- **RBAC:** `assistant/read_all`
- **Request:** Path param `userId`. Query params: `range`, `format`, `zone`.
- **Response:**
  - `200` -- `[]model.AssistantSession` (includes deleted, with usage stats)
  - `400` / `401` / `403` / `500`
- **Business logic notes:** Returns sessions for a specific user (or all users if `userId` is empty/not in path).
- **Async:** No

### GET /api/assistant/admin/{userId}/sessions/{sessionId}/history
- **Summary:** Get Session History (admin)
- **RBAC:** `assistant/read_all`
- **Request:** Path params `userId`, `sessionId`.
- **Response:**
  - `200` -- `[]model.StoredMessage` (complete history, not converted to context format)
  - `401` / `403` / `404` -- Session not found for user
  - `500`
- **Business logic notes:** Verifies session belongs to specified user (checks deleted sessions too). Returns raw history without context conversion.
- **Async:** No

---

## 19. UtilHandler (`/api/util`)

**Source:** `server/utilhandler.go`

### PUT /api/util/reverse-lookup
- **Summary:** DNS Reverse Lookup
- **RBAC:** Any authenticated user (bearer)
- **Request:** JSON body -- `[]string` (list of IP addresses).
- **Response:**
  - `200` -- `map[string][]string` (IP -> resolved domain names)
  - `400` / `401` / `500`
- **Business logic notes:**
  - Deduplicates input IPs. Validates each is a valid IP.
  - Phase 1: ES lookup in `so-ip-mappings` index via `Eventstore.MSearch()`. Maps `so.ip_address` -> `so.description`.
  - Phase 2: DNS reverse lookup for remaining unresolved IPs (only if `Config.EnableReverseLookup` is true).
  - Uses custom DNS resolver if `Config.Dns` is configured (default port 53, 3000ms timeout).
  - Parallel DNS lookups via `lop.ForEach()`.
  - Unresolvable IPs map to themselves `[ip]`.
- **Async:** No

---

## Cross-Cutting Concerns

### Authentication
- All routes are behind `web.Middleware` which handles authentication.
- OAuth2 bearer tokens (obtained via `POST /oauth2/token` with client_credentials grant).
- CSRF protection via `SrvToken` (for browser sessions, not API clients).
- API clients are CSRF-exempt.

### Authorization (RBAC)
- Two patterns used:
  1. **Explicit in handler:** `server.CheckAuthorized(ctx, operation, target)` -- returns 401 on failure.
  2. **Delegated to store:** The Casestore and some other stores perform RBAC checks internally.
- Permission format: `target/operation` (e.g. `events/read`, `detections/write`).
- Some handlers check multiple permissions with OR logic (e.g. `read_authored` OR `read_all`).

### WebSocket Broadcasts
- Several handlers broadcast real-time events via `server.Host.Broadcast(event, channel, data)`:
  - `"job"` on `"jobs"` -- job CRUD
  - `"node"` on `"nodes"` -- node check-in
  - `"import"` on `"jobs"` -- PCAP/EVTX import complete
  - `"related:bulkCreate"` on `"cases"` -- bulk event attachment complete
  - `"detections:bulkUpdate"` on `"detections"` -- bulk detection update complete

### Async Operations
- Several endpoints return immediately and process in goroutines:
  - `POST /api/case/events` (202) -- bulk related event creation
  - `POST /api/gridmembers/{id}/import` (202) -- file import
  - `POST /api/detection/bulk/{newStatus}` (202) -- bulk detection management
  - `PUT /api/users/sync` -- user synchronization
  - `POST /api/assistant/chat` (streaming) -- response save
  - `POST /api/assistant/tool/{name}` (streaming) -- response save
- These use `context.Background()` to avoid request timeout cancellation, copying `RequestorId` and `RunAsUsername` from original context.

### License Gating
- `ClientsHandler` -- all endpoints require `licensing.FEAT_API`
- `QueryHandler` -- active queries / cancel require `licensing.FEAT_QRY`
- `InfoHandler` -- subgrid count validated against license

### Error Responses
- All errors returned via `web.Respond(w, r, statusCode, err)`.
- Error bodies are typically the error message string or a structured error object.
- Some specific error strings are used as codes: `"ERROR_LICENSE_INVALID"`, `"ERROR_DELETE_COMMUNITY"`, `"ERROR_BULK_COMMUNITY"`, `"ERROR_SERVICE_NOT_AVAILABLE"`, `"ERROR_UPSTREAM_SERVICE_ERROR"`, `"ERROR_ASSISTANT_REQUEST_TOO_LARGE"`, `"ERROR_SESSION_ATTACHED_TO_CASES"`, `"ERROR_QUERY_NOT_FOUND"`, `"publicIdConflictErr"`, `"missingPublicIdErr"`.
