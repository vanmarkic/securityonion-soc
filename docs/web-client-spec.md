# Security Onion Vue 3 Web Client — Specification

> Foundation document for writing UI integration tests. Derived entirely from static reconnaissance of the existing Vue 3 client. Endpoints not observed in the source are explicitly marked **(unknown)**; nothing here is invented.

**Primary source files**
- App shell / nav markup: `/Users/dragan/Documents/securityonion-soc/html/index.html`
- Root app (global state, axios, auth, bootstrap, WebSocket, i18n, helpers): `/Users/dragan/Documents/securityonion-soc/html/js/app.js` (1929 lines)
- Static strings: `/Users/dragan/Documents/securityonion-soc/html/js/i18n.js`
- Per-view files: `/Users/dragan/Documents/securityonion-soc/html/js/routes/*.js`
- Existing unit tests: `/Users/dragan/Documents/securityonion-soc/html/js/app.test.js`, `test_common.js`, and per-route `*.test.js`

---

## 1. Overview & Architecture

The client is a **Vue 3 single-page application** built with the **global (CDN-style) build** — Vue, Vuetify, VueRouter, and supporting libraries are **vendored** as `<script>` includes; **there is no build/transpile step**. The application is assembled at runtime in the browser.

Key architectural facts:

- **Static files served by the backend on one origin.** The frontend computes its API base as `location.origin + location.pathname + 'api/'`. Same-origin is mandatory — there is no configurable API host. In the FastAPI rewrite the app runs at `http://127.0.0.1:9822` with uvicorn serving both `create_app` and the static `html/` directory.
- **Hash-based routing.** The router uses `createWebHashHistory()`, so all routes live under `#/...` (e.g. `#/alerts`, `#/case/123`). This means deep-linking and route assertions operate on the URL fragment, not the path.
- **Vuetify** is configured with the FontAwesome icon set (`'fa'`), `defaultTheme: 'dark'`, and both light and dark color palettes.
- **Two axios clients** are exposed on the Vue root component:
  - `papi` — Security Onion's own REST API (base `apiUrl = location.origin + location.pathname + 'api/'`). Has request + response interceptors.
  - `authApi` — Kratos self-service auth API (`baseURL = authUrl = '/auth/self-service/'`, `withCredentials: true`). **Does not** share `papi`'s interceptors.
  - An anonymous `papi` built via `createApi()` (no baseURL) is used by the login/home views for web-root assets (`/login/banner.md`, `motd.md`). The response interceptors still apply to it.
- **Root component holds nearly all global state** and exposes ~100 helper methods reached from views via `this.$root.*`. There is no shared mixin.

### Boot sequence

1. jQuery `$(document).ready` waits on `Promise.all(templatePromises)` — view templates are loaded via `loadPageTemplate(id, path)`, appending `<template>` elements to the body with a cache-buster from `document.currentScript.src`.
2. Build `_i18n = i18n.getLocalizedTranslations(navigator.language)`.
3. Create Vuetify, create VueRouter (hash history).
4. `Vue.createApp(comp)`, `app.use(vuetify)`, `app.use(router)`, register all `components[]` and `directives[]`, `app.mount('#app')`.
5. `created()` runs redirect checks (`redirectIfAuthCompleted()`, `redirectRoute()`), then `setupApi()` + `setupAuth()`.
6. `mounted()` registers global format helpers, loads server settings + local settings, reveals `#app` (`display: block`), and after `router.isReady()` calls `onLocationUpdated`.

### URL / timeout constants

- `apiUrl = location.origin + location.pathname + 'api/'`
- `authUrl = '/auth/self-service/'`
- `wsUrl = (https? wss:ws) + location.host + location.pathname + 'ws'`
- `settingsUrl = authUrl + 'settings/browser'`
- `connectionTimeout = 300000ms` (applies to `papi` and `authApi`; overridable via `parameters.apiTimeoutMs`)
- `wsConnectionTimeout = 15000ms` (also the reconnect interval)
- Parameter overrides from `/api/info`: `apiTimeoutMs`, `webSocketTimeoutMs`, `cacheExpirationMs`, `tipTimeoutMs`

---

## 2. Global Behavior

### 2.1 API client construction & interceptors

**`papi` (created by `setupApi()` → `createApi(apiUrl)`):**

- **Request interceptor `apiRequestCallback`** — injects the `gridId` query param from `selectedGridId` into every request, unless one is already present. Strips `gridId` when it equals `LOCAL_GRID_ID` (`''`).
- **Response interceptors** — `apiSuccessCallback` (calls `checkForUnauthorized(response)`) and `apiFailureCallback`.
- After `/api/info` succeeds, `papi.defaults.headers.common['X-Srv-Token']` is set to `response.data.srvToken`. This **server token is the app's custom anti-CSRF token**, sent on all subsequent `papi` requests. It does not exist before `/info`.
- **No axios CSRF header.** CSRF for login is Kratos-flow-based (the `csrf_token` is read from flow UI nodes and submitted by the native HTML login form).

**`authApi` (created by `setupAuth()` → `axios.create({ baseURL: authUrl, withCredentials: true })`):**

- **Bypasses** the `papi` gridId / unauthorized interceptors entirely. Used only for Kratos self-service calls.

### 2.2 401 / unauthorized / session-expiry handling

- `apiSuccessCallback` → `checkForUnauthorized(response)`.
- `apiFailureCallback`:
  - status **502–504** → sets `reconnecting = true` (**note: bare global variable, not `this.reconnecting`** — a known quirk).
  - otherwise → `checkForUnauthorized(error.response)` then re-throws.
- `checkForUnauthorized()` calls `showLogin()` (`location.href = authUrl + 'login/browser'`) and returns `null` when **any** of:
  - response `content-type` is `text/html` (a session-expired HTML login page was returned), **OR**
  - `status == 401` on a **non-`/api/`** URL, **OR**
  - an `AUTH_REDIRECT` cookie is present on a non-banner URL (the cookie is deleted before redirecting).
- A `CanceledError` (axios abort) is **downgraded to a tip** (`showTip` with `i18n.requestCanceled`), not surfaced as an error.

### 2.3 Auth-redirect cookie flow

- `created()` first calls `redirectIfAuthCompleted()`: if not on `/login` and an `AUTH_REDIRECT` cookie exists (and the destination is not a static asset), navigate to it (post-login deep-link restore).
- `redirectRoute()` handles a `?r=` param → sets `location.hash` and removes `r`.
- Cookie helpers: `setCookie` / `getCookie` / `deleteCookie` (all `Path=/`).

### 2.4 `/api/info` bootstrap

`loadServerSettings(background)` is the single bootstrap that hydrates the shell. It is:
- **DOM-gated** on the presence of a `#version` element (only present past the login screen — so it is skipped on the login screen), and
- **time-throttled** by `cacheRefreshIntervalMs` (default `300000ms`, tracked via `loadServerSettingsTime`).

It calls `papi.get('info', { params: { gridId: LOCAL_GRID_ID } })` — the subgrid override is **forced off** for this call.

| HTTP | Path | Trigger | Request | Response (fields the shell depends on) |
|---|---|---|---|---|
| GET | `api/info` | `loadServerSettings()` on mount, on WebSocket open/status, per subgrid in `loadSubgridInfo()` | query `gridId` (forced `LOCAL_GRID_ID` for primary call) | `{ srvToken, version, elasticVersion, mgmtMac, license, licenseKey:{name,features[],expiration,subgrids}, licenseStatus, parameters:{ apiTimeoutMs, webSocketTimeoutMs, cacheExpirationMs, tipTimeoutMs, tools[], inactiveTools[], casesEnabled, detectionsEnabled, exportNodeId, releaseNotesUrl, docsUrl, cheatsheetUrl }, timezones[], subgrids[], customReports, userId, forceUserOtp }` |

On a successful response the shell sets / derives:
- `X-Srv-Token` header (from `srvToken`); `version`, `mgmtMac`, `license`, `licenseKey` (old licenses default `subgrids = 0`), `licenseStatus` (active / exceeded / expired / invalid / pending / unprovisioned → warnings).
- `parameters`, `elasticVersion`, `timezones`, `subgrids`, `exportNodeId` (= `parameters.exportNodeId`), `customReports`.
- `user` (await `getUserById(userId)`) and `username` (= `user.email`).
- Parameter overrides: `webSocketTimeoutMs`, `apiTimeoutMs`, `cacheExpirationMs`, `tipTimeoutMs`.
- `tools` (with `inactiveTools` toggling `tool.enabled`), `casesEnabled`, `detectionsEnabled`.
- Runs `checkUserSecuritySettings` — if `forceUserOtp`, redirect hash to `/settings?tab=security`.
- Subscribes WebSocket handlers (`status`, `import`, `detection-sync`).
- Stores `gridInfo[LOCAL_GRID_ID] = data` and loops `loadSubgridInfo()` per subgrid.
- **Errors are only shown on the initial (non-background) load.** Background `/info` failures are silent; connectivity is signalled via the nav indicator.

`isLicensed(feat)` is gated by `licenseKey.features` + `licenseStatus`. Known feature flags: `FEAT_RPT = 'rpt'`, `FEAT_TTR = 'ttr'`, `FEAT_OAI = 'oai'`, plus `'api'` and `'qry'`.

### 2.5 i18n

`i18n.getLocalizedTranslations(navigator.language)` returns `translations[lang]` or falls back to `translations['en-US']` (the only fully-populated locale). It is a **static JS object** loaded via `<script>` — **no network fetch**. Stored as root data `i18n` (= `_i18n`), used everywhere via `this.i18n.*` / `$root.i18n.*`.

Helpers: `localizeMessage(msg, vars)` (unwraps `error.response.data.error.reason`, strips quotes, looks up i18n key, `{var}` interpolation, truncates > 200 chars), `tryLocalize`, `correctCasing` (`cc_<lower>` keys, e.g. `cc_elastalert`).

### 2.6 Navigation shell (`index.html`)

Nav items are `router-link`s gated by license/role/feature flags:

| Nav item | Route | Visibility gate |
|---|---|---|
| Overview | `/` | always |
| Assistant | `/assistant` | (assistant enabled) |
| Alerts | `/alerts` | always |
| Dashboards | `/dashboards` | always |
| Hunt | `/hunt` | always |
| Cases | `/cases` | `v-if casesEnabled` |
| Detections | `/detections` | `v-if detectionsEnabled` |
| Jobs | `/jobs` | always |
| Grid | `/grid` | always |
| Downloads | `/downloads` | always |
| Reports | `/reports` | `v-if isLicensed(FEAT_RPT)` |
| **Admin group** | | |
| Users | `/users` | admin |
| API Clients | `/clients` | `isLicensed('api') && isUserAdmin` |
| Active Queries | `/queries` | `isLicensed('qry') && admin` |
| Grid Members | `/gridmembers` | admin |
| Config | `/config` | admin |
| License Key | `/licensekey` | admin |
| AI Metrics | `/aimetrics` | `admin && isLicensed('oai')` |

User menu: release notes / docs / cheatsheet / blog / pro / hardware / support (external links from `parameters.*`), profile settings (`settingsUrl = authUrl + 'settings/browser'`), and logout. Footer terms/license link chosen by `licenseStatus`.

### 2.7 Subgrid / grid selector

- `selectedGridId` defaults to `LOCAL_GRID_ID` (`''`).
- Watcher `onGridSelected` pushes `gridId` into the route query; `onLocationUpdated` reads `gridId` back from the query.
- `checkSubgridSelectorEnabled` **disables** the selector on `SUBGRID_DISABLED_ROUTES = ['home','settings','assistant','aimetrics']`.
- `apiRequestCallback` auto-injects the selected `gridId` into every `papi` request.

### 2.8 WebSocket (live updates) — no SSE in `app.js`

- `ensureConnected()` / `openWebsocket()` opens a `WebSocket` to `wsUrl`; `setInterval(openWebsocket, wsConnectionTimeout)` is the reconnect loop.
- `onopen` → sets `connected`, resets `loadServerSettingsTime = 0` (forces an info reload) and calls `updateStatus()`.
- `onmessage` → `JSON.parse` → `publish(msg.Kind, msg.Object)`. `subscribe` / `unsubscribe` / `publish` implement an in-memory pub/sub keyed by message `Kind`.
- If the socket is already open, a `{"Kind":"Ping"}` keep-alive is sent each interval.
- `updateStatus(status)` stores status by `gridId`, refreshes favicon/title, and triggers a background `loadServerSettings`.
- Connection state (`connected` / `reconnecting`) drives `isAttentionNeeded()` and the nav connectivity indicator.

**Streaming (SSE) lives only in the assistant view**, not `app.js`. `assistant.js` uses `papi` with `responseType: 'stream'`, `Accept: 'text/event-stream'`, `adapter: 'fetch'`, and reads `stream.pipeThrough(new TextDecoderStream()).getReader()` for Anthropic-style `content_block_*` chunks from `/api/assistant/chat` and `/api/assistant/tool/<name>`.

### 2.9 Global loading / error / snackbar state

Root data + methods rendered by snackbars in `index.html`. These are the **integration-test assertion seams**:

- Booleans + `*Message` strings + timeouts: `error` (`errorTimeout 120000`), `warning` (`warningTimeout 30000`), `info`, `tip` (`tipTimeout 6000`, overridable, `currentTipTimeout`), `disclaimer`.
- `showError(e)` — localizes, logs stack if debug, special-cases `CanceledError` → tip.
- `showWarning(msg, skipLocalization?)`.
- `showInfo(msg)` — raw.
- `showTip(msg)` — clears error/warning/info first.
- `showDisclaimer(...)` — `localStorage`-gated by `storageKey`; `acceptDisclaimer` persists `'true'`; `closeDisclaimerOnNav` on route change.
- `startLoading(cancelCallback)` / `stopLoading()` toggle the global `loading` overlay (`loadingCancelCallback` enables the cancel affordance).

**View loading pattern:** views wrap `papi` calls with `$root.startLoading()` / `$root.stopLoading()` and call `$root.showError(e)` in `catch`.

### 2.10 Theme / favicon / title

- `theme = Vuetify.useTheme()`; `toggleTheme` persists to `localStorage['settings.app.dark']` and updates the (Prism) editor CSS.
- `loadLocalSettings` restores theme + toolbar (`localStorage['settings.app.navbar']`).
- `setFavicon` swaps the favicon by `prefers-color-scheme` + attention state; `updateTitle` prefixes `'! '` and appends a subtitle when attention is needed (new alerts, unhealthy grid/detections, disconnected/reconnecting).

### 2.11 Shared root helpers used by views

Reached via `this.$root.*` (selected, relevant to API behavior):
- `getUsers()` → GET `users/`; `getAllUsers()` (loops grids); `getUserById(id)` → GET `users/{id}` (cache-backed); `getActiveUsers()` → GET `users/?gridId=`.
- `populateUserDetails()` — resolves display names from a cached user list (no per-call HTTP in common path).
- `batchLookup(ips, comp)` → PUT `util/reverse-lookup` (gridId forced `LOCAL_GRID_ID`; calls `comp.$forceUpdate()`).
- `export(params, beginDate, endDate)` → POST `job/` `{ kind:'reports', nodeId: exportNodeId, filter:{ beginTime, endTime, parameters } }` (wraps start/stop loading).
- `loadParameters(section, cb)` — reads pre-fetched `this.parameters[section]` (loaded once from `/info`); **not** a per-view HTTP call.
- `logout()` → GET `/auth/self-service/logout/browser` via `authApi`, then `location.href = response.data.logout_url`.

### 2.12 Notable subtleties (for test design)

1. `apiFailureCallback` leaks `reconnecting = true` to global scope for 502–504.
2. `checkForUnauthorized` treats **any** `text/html` response as session-expiry.
3. `gridId` is auto-injected on every `papi` request and stripped when empty; `info` and `reverse-lookup` force `LOCAL_GRID_ID`.
4. `X-Srv-Token` exists only after `/info` succeeds.
5. `authApi` bypasses gridId/unauthorized interceptors.
6. `loadServerSettings` is DOM-gated on `#version` and time-throttled.
7. Background `/info` errors are suppressed.
8. Editor / charts / mermaid are lazily initialized once.
9. `maximize` / `unmaximize` add a `maximized` class + an Escape keydown listener.

---

## 3. Per-View Specifications

### 3.1 Home / Overview

- **Route:** `/` (name `home`)
- **File:** `html/js/routes/home.js` (33 lines)
- **Purpose:** Landing page rendering the Message-of-the-Day (MOTD) from markdown.

| HTTP | Path | Trigger | Request | Response |
|---|---|---|---|---|
| GET | `motd.md?v=<timestamp>` | `created()` → `loadChanges()` on load; cache-busted `v=Date.now()` | query `v=epoch-ms` | raw markdown text → `this.motd` |

- **Key interactions:** none; auto-loads MOTD on `created()`.
- **Note:** uses the generic `createApi()` (web-root base), **not** `papi`. The MOTD is a **static asset** — this view does **not** hit `/api`.
- **WebSocket/streaming:** none.

---

### 3.2 Hunt / Alerts / Dashboards / Detections / Cases-list (shared `huntComponent`)

- **Routes:** `/hunt`, `/alerts`, `/dashboards`, `/detections`, `/cases` (one component, five routes; branches on `this.category`)
- **File:** `html/js/routes/hunt.js` (3342 lines)
- **Purpose:** Core events/alerts search and visualization. Runs a query over a date range; renders timeline chart, top/bottom aggregation charts, group-by tables, and an events table. `/alerts` adds ack/escalate, AI investigation, playbooks; `/detections` adds bulk enable/disable/delete and manual engine sync.

**Query model:** `this.query` is a Security Onion query-language string with optional `| groupby` / `| table` / `| sortby` segments. Filter toggles are composited server-side via GET `query/filtered` (`scalar=true`, `mode=INCLUDE`, `condense=true`) in `getQuery()` before the main `events/` search.

| HTTP | Path | Trigger | Request shape | Response shape |
|---|---|---|---|---|
| GET | `events/` | `loadData()` — primary search on hunt/route change/autohunt/auto-refresh; cancellable via AbortController | `{ query: <composited>, range: '<from> - <to>', format: i18n.timePickerSample, zone, metricLimit: groupByLimit, eventLimit, [gridId] }` | `{ totalEvents, elapsedMs, completeTime, createTime, events:[{id,score,type,timestamp,source,payload:{...}}], metrics:{ timeline:[...], top/<key>:[...], bottom:[...], <groupby>:[...] } }` |
| GET | `events/` | `fetchNewestEvent(item)` — newest matching event for a grouped alert (before AI investigation / playbook load) | `{ query: '<field:"value" AND ... > \| sortby @timestamp', range, format, zone, metricLimit:0, eventLimit:1, [gridId] }` | `{ events:[{...}] }` — first event's `soc_*` extracted |
| GET | `query/filtered` | `getQuery()` composites filters before every search; `filterQuery()` for quick-action include/exclude/exact/drilldown/numeric | `{ query, field, value, scalar, mode: INCLUDE\|EXCLUDE\|EXACT\|DRILLDOWN, [condense:true] }` | string — new combined query expr → `this.query` |
| GET | `query/grouped` | `groupQuery()` — quick-action group-by / group-by (new) | `{ query, field, group }` | string — new query expr with groupby segment |
| POST | `events/ack` | `ack()` on `/alerts` (escalate on `/hunt`) — Acknowledge / Ack-undo / Escalate one or all matching events | `{ searchFilter, eventFilter:{<fields>}\|{'rule.uuid':uuid}, dateRange, dateRangeFormat: i18n.timePickerSample, timezone, escalate, acknowledge }` | `{ errors:[...] }` — non-empty → partial-success warning |
| POST | `case/` | `ack(...escalate=true)` when no target case / related-events disabled — create a case from the alert (`buildCase`) | `{ title, description, severity, template }` from alert fields | `{ id, ... }` — id used to attach events |
| POST | `case/events` | `ack(...escalate=true)` with `escalateRelatedEventsEnabled` — attach escalated event(s) to a case | `{ fields, caseId, acknowledged, escalated, dateRange, dateRangeFormat, timezone }` | association data; bulk progress via `related:bulkCreate` subscription |
| GET | `detection/public/{publicId}` | `toggleQuickAction()` / `highlightDetection()` on `/alerts` — fetch detection backing an alert (`rule.uuid`) | path `publicId` (= `rule.uuid`) | detection `{ id, engine, publicId, ... }` → `highlightedDetection` / `quickActionDetId` |
| POST | `detection/bulk/{action}` | `bulkAction()` on `/detections` — bulk enable/disable/delete | `{ query }` (select-all) OR `{ ids:[<soc_id>...] }` | `{ count }` queued; async via `detections:bulkUpdate` subscription |
| POST | `detection/sync/{engine}/{type}` | `startManualSync()` on `/detections` — manual full/update sync | path `engine` + `type` (`'full'` or other); no body | fire-and-forget (not awaited); success tip |
| GET | `playbook/event/{socId}` | `loadPlaybook(event)` on `/alerts` — playbooks + answered questions for an alert's `soc_id` | path `socId` | `[{ questions:[{ fields, queryResults:[{payload}], ... }] }]` — sorted; IPs batch-looked-up |
| POST | `job/` | `exportEvents()` / `exportMetrics()` via `$root.export()` — tabular export job | `{ kind:'reports', nodeId: exportNodeId, filter:{ beginTime, endTime, parameters:{ type:'tabular', query, [group, groupIdx], timezone } } }` | `{ id }` — export job id in tip |

- **Key interactions:** query input (advanced vs simple; Enter = `submitQuery` or autohunt-on-change); saved/predefined queries dropdown + MRU history (localStorage); relative/absolute time range + auto-refresh selector; filter toggle chips (acknowledged, escalated, investigated, caseExclude, detectionsExclude, socExclude, onionaiExclude); quick-action popups (include/exclude/exact/drilldown/numeric/group-by); group-by tables (limit, per-page, sort, filter, export metrics); events table (per-page, sort, event limit, row expand, export events); alerts-only ack/escalate (single, grouped, "many" confirm), add-to-existing-case dialog (MRU cases), AI Investigation → assistant route, playbook tab; detections-only select-all/per-row + bulk action selector with delete confirm + manual sync + engine status hunt links.
- **URL query params drive state:** `q, t, rt/rtu, z, el, gl, ar, tab, expand, gridId, filterField/Value/Mode/scalar, groupByField/Group`, and per-toggle names.
- **WebSocket:** subscribes to `detections:bulkUpdate` and `related:bulkCreate` for async bulk progress (push, not request).
- **Settings:** persisted to localStorage (not API).

---

### 3.3 Case detail

- **Route:** `/case/:id` (also `/case/create` → create-then-redirect)
- **File:** `html/js/routes/case.js` (1129 lines)
- **Purpose:** View/edit a single case and its associations: comments, attachments, evidence (artifacts), related events, audit history. Inline editing, file uploads, evidence analyzers, hunting related events, export.

> `mapAssociatedPath`: both `attachments` and `evidence` map to the **artifacts** endpoint; `concatPath` appends `/attachments` or `/evidence` for list GETs.

| HTTP | Path | Trigger | Request shape | Response shape |
|---|---|---|---|---|
| POST | `case/` | `createCase()` on `/case/create` — create default case then `router.replace` to `/case/:id` | `{ title: i18n.caseDefaultTitle, description: i18n.caseDefaultDescription }` | `{ id, ... }` → redirect |
| GET | `case/` | `loadData()` on mount/route change | `{ id: <route id> }` | case `{ id, title, description, severity, status, userId, assigneeId, tlp, pap, tags, createTime, updateTime, ... }` |
| PUT | `case/` | `modifyCase()` — save inline-edited field | `JSON.stringify(case form)` (changed field merged; `kind`/`operation` stripped) | updated case object |
| GET | `case/comments` | `loadAssociation('comments')` | `{ id: caseId, offset, count: <default 500> }` | `[ comment {id, userId, description, hours, createTime, updateTime} ]` |
| GET | `case/artifacts/attachments` | `loadAssociation('attachments')` (concatPath) | `{ id: caseId, offset, count }` | `[ artifact {id, groupType, value, createTime, updateTime, tlp, tags} ]` |
| GET | `case/artifacts/evidence` | `loadAssociation('evidence')` | `{ id: caseId, offset, count }` | `[ artifact {id, artifactType, value, ...} ]` — IP values batch reverse-looked-up |
| GET | `case/events` | `loadAssociation('events')` | `{ id: caseId, offset, count }` | `[ event assoc {id, fields:{soc_timestamp, soc_id, event.module/category/dataset}} ]` |
| GET | `case/history` | `loadAssociation('history')` | `{ id: caseId, offset, count }` | `[ history {id, userId, updateTime, kind, operation} ]` |
| POST | `case/comments` | `addComment()` / `addAssociation('comments')` | `JSON.stringify({ caseId, id:'', description, hours, ... })` | created comment |
| POST | `case/artifacts` | `addAssociation('attachments'\|'evidence')` | File: `multipart/form-data` (`json` = stringified `{caseId,id:'',artifactType:'file',tlp,tags}` + `attachment` file). Evidence: `JSON.stringify({caseId,id:'',artifactType,value,tlp,description})`; bulk = one request per newline value | created artifact |
| PUT | `case/comments` | `modifyAssociation('comments', obj)` | `JSON.stringify(changed comment)` | updated comment |
| PUT | `case/artifacts` | `modifyAssociation('attachments'\|'evidence', obj)` | `JSON.stringify(changed artifact)` | updated artifact |
| DELETE | `case/comments` \| `case/artifacts` \| `case/events` \| `case/history` | `deleteAssociation(association, obj)` (attachments/evidence → `case/artifacts`) | `{ id: <row id> }` | 204/empty |
| POST | `job/` | `analyze(evidence)` — enqueue analyzer job | `{ kind:'analyze', nodeId: analyzerNodeId, filter:{ parameters:{ artifact: <evidence obj> } } }` | job (tip); live via `job` subscription |
| GET | `jobs/` | `loadAnalyzeJobs(artifactId)` when evidence row expanded | `{ kind:'analyze', parameters:{ artifact:{ id: artifactId } } }` | `[ job {id, status, filter:{...}, results:[...]} ]` |
| DELETE | `job/{job.id}` | `deleteAnalyzeJob(job)` | path job id; no body | 204/empty |
| POST | `job/` | `exportCase()` via `$root.export()` | `{ kind:'reports', nodeId, filter:{ parameters:{ type:'case', id: caseId } } }` | `{ id }` |
| GET | `users/` | `loadData()` → `getActiveUsers()` for owner/assignee selectors | `{ gridId }` | `[ user {id, email, ...} ]` |

- **Key interactions:** inline edit of case fields (`onDetailsSave` → `modifyCase`); sections/tables (comments, attachments, evidence, events, history) with search/sort/per-page; add comment (with hours); add attachment (multipart); add evidence/observable (single or bulk newline-separated; artifactType auto-detected by regex; tlp, tags); edit/delete rows; evidence row expand → analyzer jobs; hunt related events (`huntCase` → navigate to hunt route); export. URL `?type=` selects tab, `?value=` pre-fills evidence observable. MRU cases in localStorage.
- **WebSocket:** subscribes to `case` and `job` channels.

---

### 3.4 Detection detail

- **Route:** `/detection/:id` (also `/detection/create`)
- **File:** `html/js/routes/detection.js` (1425 lines)
- **Purpose:** View/create/edit a single detection rule (Suricata, ElastAlert/Sigma, Strelka/YARA). Shows extracted summary/references/logic, overrides, comments, history, playbooks. Save/duplicate/convert + engine-sync warnings.

> **Inconsistent leading slash:** create/edit use `'/detection'` (POST/PUT); reads use `'detection/...'` (no leading slash). Both resolve under the `papi` `/api/` base. `languageToEngine`: sigma→elastalert, suricata→suricata, yara→strelka.

| HTTP | Path | Trigger | Request shape | Response shape |
|---|---|---|---|---|
| GET | `detection/{id}` | `loadData()` (non-create); id URL-encoded | path `id` (`encodeURIComponent`) | detection `{ id, publicId, title, description, engine, language, content, severity, isEnabled, isReporting, isCommunity, overrides:[...], aiSummary, aiSummaryReviewed, userId }` |
| GET | `detection/{engine}/genpublicid` | `onNewDetectionLanguageChange()` in create flow (non-strelka) | path `engine` (`suricata`\|`elastalert`) | `{ publicId }` |
| POST | `/detection` | `saveDetection(createNew=true)` | detection object | created `{ id }` → `router.push` to `/detection/:id` |
| PUT | `/detection` | `saveDetection(createNew=false)` (also inline edits, override add/edit/delete); `validateStatus` accepts 200–299 | full detection object (overrides cleaned via `cleanupOverrides`) | updated detection; status `205`/`206` → warnings |
| POST | `/detection/{id}/duplicate` | `duplicateDetection()` | path `id` (`encodeURIComponent`); no body | new `{ id }` → `router.push` |
| PUT | `/detection/{detectId}/override/{index}/note` | `saveOverrideNote(item)` | `{ note: <text> }` | empty/ok |
| GET | `detection/{id}/history` | `loadHistory()` | path `id` | `[ history {...} ]` |
| GET | `detection/{detectId}/comment` | `loadComments()` via `loadAssociations()` | path detection id | `[ comment {id, userId, assigneeId, value, description, operation, createTime, updateTime} ]` |
| POST | `detection/{detectId}/comment` | `addComment()` (new) | `JSON.stringify({ detectionId, id:'', value, ... })` | created comment |
| PUT | `detection/comment/{commentId}` | `addComment()` (edit, `origComment` set) | `JSON.stringify({ id, detectionId, value, ... })` | updated comment |
| DELETE | `detection/comment/{commentId}` | `deleteComment(obj)` | path comment id; no body | 204/empty |
| GET | `playbook/detection/{publicId}?raw=true` | `loadPlaybooks()` via `loadAssociations()` | path `publicId`; query `raw=true` | raw playbook YAML; split on `\n---\n` for count |
| POST | `detection/convert` | `convertDetection()` — Sigma → backing query | detection object (`this.detect`) | `{ query }` → sigma dialog / copy / Kibana dev tools |

- **Save status codes:** `205` effected-by-filter, `206` disabled-failed-sync, `409` publicId conflict, `423` sync-blocked.
- **Key interactions:** create flow (pick language → fetch public id + seed template); inline edit (community rules only allow toggling `isEnabled`); source editor with highlight + dirty-source confirm + client-side syntax validation; overrides table (elastalert customFilter; suricata modify/suppress/threshold); tabs overview/source, tuning, comments, history, playbooks (`?tab=`); comments add/edit/delete; history table with diff highlighting; duplicate; convert dialog (copy + "run in Discover/Kibana" opens a Kibana URL, **not** `/api`).
- **WebSocket/streaming:** none observed in this file.

---

### 3.5 Jobs / PCAP

- **Route:** `/jobs` (name `jobs`, `pcapComponent`)
- **File:** `html/js/routes/jobs.js`
- **Purpose:** List/create/view/delete PCAP capture jobs. The same component is reused for the reports route. Data table with status, owner, sensor, queued/completed times, per-row actions.

| HTTP | Path | Trigger | Request shape | Response shape |
|---|---|---|---|---|
| GET | `/api/jobs` | `loadData()` on created, `$route` change, 500ms after `submitAddJob` | query `{ kind: 'pcap' }` (derived from route) | `Array<Job>`: `{ id, userId, owner, createTime, completeTime, sensorId/nodeId, status (0=Pending,1=Completed,2=Incomplete,3=Deleted), size, fileExtension, filter:{ srcIp, srcPort, dstIp, dstPort, beginTime, endTime, parameters } }` |
| POST | `/api/job/` | `addJob()` via `submitAddJob()` (Add Job dialog) | `{ nodeId:<sensorId>, filter:{ importId, protocol(lowercased), srcIp, srcPort(int), dstIp, dstPort(int), beginTime?(ISO8601), endTime?(ISO8601) } }` | created Job (pushed after `populateUserDetails`) |
| DELETE | `/api/job/{id}` | `deleteJob(job)` per-row delete | path `job.id`; no body | no body used; row filtered out locally |
| GET | `/api/stream` | `downloadUrl(job)` builds href (`apiUrl + 'stream?jobId='+job.id`); user-navigated, **not** axios | query `{ jobId }` | binary PCAP/stream download |

- **Key interactions:** Add Job dialog (`openNewJobDialog`) with daterangepicker; form persisted to localStorage (`settings.jobs.addJobForm.*`); `submitAddJob` branches (kind `reports` → `addExportJob` via `$root.export`, otherwise `addJob`); per-row gating (`isViewable`, `isDownloadable`, `isDownloadReady` = complete && size>0, `canCreate`, `isSensorJob`); sort/per-page in localStorage.
- **WebSocket:** subscribes to `job` topic; `updateJob()` patches/removes rows on push (status Deleted splices it out).
- **Constants:** JobStatus 0 Pending, 1 Completed, 2 Incomplete, 3 Deleted.

---

### 3.6 Reports (Export/Report jobs)

- **Route:** `/reports` (name `reports`, `reportsComponent` = clone of `jobsComponent`)
- **File:** reuses `jobs.js`
- **Purpose:** Reuses the jobs component to list/create report/export jobs. Reports are downloadable, not viewable; creation is licensed (`FEAT_RPT`).

| HTTP | Path | Trigger | Request shape | Response shape |
|---|---|---|---|---|
| GET | `/api/jobs` | `loadData()` on created/`$route` change | query `{ kind: 'reports' }` | `Array<Job>`; `getDescription` reads `job.filter.parameters.{description,type,id}` + `job.fileExtension` |
| DELETE | `/api/job/{id}` | `deleteJob(job)` per-row delete | path `job.id` | removed locally on success |

- **Key interactions:** `submitAddJob` → `addExportJob()` parses timeframe into begin/end then calls `$root.export({ type, description }, beginDate, endDate)` — **report creation is delegated to the root `export`, not a direct POST in this file**; `canCreate()` = `isLicensed(FEAT_RPT)`; report types = `standardReportTypes` (productivity) + `$root.getCustomReports()`; uses `reportHeaders` (description, filesize columns).
- **Note:** the only direct REST in the reports path is GET `/api/jobs` and DELETE `/api/job/{id}`.

---

### 3.7 Job (single job / PCAP viewer)

- **Route:** `/job/:jobId` (name `job`)
- **File:** `html/js/routes/job.js`
- **Purpose:** Detail view for a single job: metadata + paginated captured packets, hex/ascii/unwrap rendering, transcript export to CyberChef, PCAP download.

| HTTP | Path | Trigger | Request shape | Response shape |
|---|---|---|---|---|
| GET | `/api/job/` | `loadData()` on mounted / `$route` change | query `{ jobId: route.params.jobId }` | Job `{ id, status, userId, owner, filter:{ srcIp, srcPort, dstIp, dstPort, ... } }`; triggers `batchLookup` of src/dst IPs |
| GET | `/api/packets` | `loadPackets(unwrap)` from `loadData`, `updateJob` on status change, `toggleWrap()` | query `{ jobId, offset: packets.length, count: 500, unwrap:<bool> }` | `Array<Packet>` appended: `{ number, timestamp, type, srcIp, srcPort, dstIp, dstPort, flags, length, payload(base64), payloadOffset }`. **404 silently ignored** (no packets yet) |
| GET | `/api/stream` | `downloadUrl()` builds href (`apiUrl + 'stream?jobId=...&ext=pcap&unwrap=<bool>[&gridId=<id>]'`); user-initiated, **not** axios | query `{ jobId, ext:'pcap', unwrap:<bool>, gridId?:selectedGridId }` | binary PCAP download |

- **Key interactions:** packet pagination via offset/count=500 infinite-append; quick-action menu from `loadParameters('job')` actions (+ text-selection actions); render options `packetOptions ['packets','hex','unwrap']` + `expandAll` (localStorage `settings.job.*`); `transcriptCyberChef()` opens `/cyberchef/` window and injects hexdump transcript; `toggleWrap()` clears packets and reloads with flipped unwrap flag.
- **WebSocket:** subscribes to `job` topic; `updateJob()` reloads packets when status changes and replaces `this.job`.
- **Note:** `papi.get('job/')` (single, trailing slash, jobId as query) is distinct from the list's `papi.get('jobs')`.

---

### 3.8 Grid (Grid Overview)

- **Route:** `/grid` (name `grid`)
- **File:** `html/js/routes/grid.js`
- **Purpose:** Operational dashboard of all grid nodes/sensors: status, role, metrics (EPS, CPU/mem/disk, traffic, loss, pcap retention), container health, and admin actions (test, restart, upload PCAP/EVTX).

| HTTP | Path | Trigger | Request shape | Response shape |
|---|---|---|---|---|
| GET | `/api/grid` | `loadData()` from `initGrid` (after `loadParameters('grid')`) and `$route` change | no params | `Array<Node>`: `{ id, gridId, role, address, version, model, status (unknown/fault/ok/pending/restart), updateTime, metricsEnabled, consumptionEps, memoryUsedPct, diskUsedRootPct, diskUsedNsmPct, cpuUsedPct, traffic*Mbs, *LossPct, pcapDays, uptimeSeconds, processJson, keywords, suriRulesStatus/Loaded/Failed }` |
| POST | `/api/gridmembers/{nodeName}/test` | `gridMemberTest()` after confirm (admin + Sensor) | path `nodeName` = `id + '_' + role.replace('so-','')`; body null; query `{ gridId: selectedNode.gridId }` | no body; success tip `gridMemberTestSuccess` |
| POST | `/api/gridmembers/{nodeName}/restart` | `gridMemberRestart()` after confirm (admin) | path `nodeName`; body null; query `{ gridId }` | no body; success tip `gridMemberRestartSuccess` |
| POST | `/api/gridmembers/{nodeName}/import` | `gridMemberUpload()` after picking file + confirm (PCAP for Sensor/Import, EVTX for Manager) | `multipart/form-data` FormData field `attachment`; query `{ gridId }`. Client max size default 25MiB (overridable `params.maxUploadSize`) | no body; success `gridMemberUploadSuccess`; HTTP 409 → `gridMemberUploadConflict`; other → `gridMemberUploadFailure` |

- **Key interactions:** `initGrid` sets `maxUploadSize`, `staleMetricsMs`, guesses timezone, starts 30s staleness interval; action gating `canTest` (admin+Sensor), `canRestart` (admin), `canUpload`/`canUploadPCAP` (Sensor|Import, not so-heavynode) / `canUploadEvtx` (Manager); confirmation dialogs; per-node container health; `dashboardLink` to metrics URL; `generateContainerLink` builds a hunt-query route link; responsive metrics columns; settings in localStorage (`settings.grid.*`).
- **WebSocket:** subscribes to `node` (`updateNode` merges/adds node, recomputes metrics columns) and `status` (`updateStatus` sets `gridEps`).
- **Note:** `nodeName` = `getNodeName(node)` = `node.id + '_' + node.role.replace('so-','')`.

---

### 3.9 Grid Members (Grid Membership Management)

- **Route:** `/gridmembers` (name `gridmembers`)
- **File:** `html/js/routes/gridmembers.js`
- **Purpose:** Manage Salt minion / node membership: list members grouped by status (accepted, unaccepted, rejected, denied) and accept (add), reject, or delete (remove) them.

| HTTP | Path | Trigger | Request shape | Response shape |
|---|---|---|---|---|
| GET | `/api/gridmembers/` | `loadData()` from `initGrid` (after `loadParameters('gridmembers')`), `$route` change, and after each mutation | no params (trailing slash) | `Array<Member>`: `{ id, status ('accepted'\|'unaccepted'\|'rejected'\|'denied'), ... }`; split client-side, sorted by id |
| POST | `/api/gridmembers/{id}/add` | `accept(node)` | path `node.id`; no body | no body; reload + tip `gridMemberAcceptSuccess` |
| POST | `/api/gridmembers/{id}/reject` | `reject(node)` | path `node.id`; no body | no body; reload on success |
| POST | `/api/gridmembers/{id}/delete` | `remove(node)` after confirm | path `node.id`; no body | no body; reload on success |

- **Key interactions:** member detail dialog with `confirmRemove`/`cancelRemove` delete confirmation; grouped/sorted by status via `localeCompare`; `colorNodeStatus` maps rejected→error, accepted→success, denied→warning.
- **WebSocket:** none; relies on explicit reload after each mutation.
- **Note:** action ids are raw `node.id` (no role suffix), unlike `grid.js` which uses `id_role`. List endpoint uses a trailing slash.

---

### 3.10 Downloads (Agent Downloads)

- **Route:** `/downloads` (name `downloads`)
- **File:** `html/js/routes/downloads.js`
- **Purpose:** Static informational page offering downloads (remote/elastic agent installers). Determines remote-agent support and the manager base URL for links.
- **API calls:** **none** (no REST/papi in this route). Download links live in `pages/downloads.html`.
- **Key interactions:** `getBaseUrl()` returns `$root.getSelectedGrid().managerUrl` when a remote grid is selected, else `''`.
- **WebSocket:** subscribes to `node` topic; `updateNode()` sets `remoteAgentSupported = false` when any node role is `so-eval` or `so-import`.

---

### 3.11 Queries (Active Queries / Tasks)

- **Route:** `/queries` (name `queries`)
- **File:** `html/js/routes/queries.js`
- **Purpose:** List currently running backend query tasks across the grid and allow cancelling one.

| HTTP | Path | Trigger | Request shape | Response shape |
|---|---|---|---|---|
| GET | `/api/query/active` | `loadData()` on created, `$route` change, and on `filterEnabled` toggle | query `{ filter: 'true'\|'false' }` | `Array<QueryTask>`: `{ taskId, gridId, details, elapsedMs, ... }` |
| POST | `/api/query/cancel/{taskId}` | `cancelQuery()` after confirm | path `cancelQueryTask.taskId`; body `{ gridId: cancelQueryTask.gridId }` | no body; success tip `queryCanceled` |

- **Key interactions:** `filterEnabled` toggle re-runs `loadData` (watch) and is sent as `filter`; cancel confirmation dialog; sort/per-page in localStorage; `adjustSubgridColVisibility` tweaks the gridId column.
- **WebSocket:** none; fetched on demand.

---

### 3.12 Users

- **Route:** `/users` (name `users`)
- **File:** `html/js/routes/users.js`
- **Purpose:** Admin CRUD for SOC users: list with roles/status, add, edit profile, change password, add/remove roles, enable/disable (lock), delete, sync with the IdP.

| HTTP | Path | Trigger | Request shape | Response shape |
|---|---|---|---|---|
| GET | `users/` (via `$root.getUsers()`) | `loadData()` on created/`$route` change; re-fetched after every mutation | — | `Array<User{id,email,firstName,lastName,note,roles[],status}>` |
| GET | `roles/` | `loadData()` | none | `Array<string>` role names (excludes `'agent'`) |
| POST | `users/` | `add()` (Add User dialog) | `{email,password,roles:[role],firstName,lastName,note}` | created user (then `getUsers` re-fetched) |
| PUT | `users/{id}` | `updateProfile(user)` | `{firstName,lastName,note}` | updated user |
| POST | `users/{id}/role/{role}` | `addRole(user,role)` | empty body | ok |
| DELETE | `users/{id}/role/{role}` | `removeRole(user,role)` | — | ok |
| PUT | `users/{id}/password` | `updatePassword(user)` | `{password}` | ok |
| PUT | `users/{id}/enable` | `toggleStatus(user)` when `status=='locked'` (unlock) | — | ok |
| PUT | `users/{id}/disable` | `toggleStatus(user)` when enabled (lock) | — | ok |
| DELETE | `users/{id}` | `removeUser(id)` (confirm delete) | — | ok (row spliced locally) |
| PUT | `users/sync` | `sync()` button | — | ok (then `getUsers` re-fetched) |

- **Key interactions:** expandable table (one row at a time via `onlyExpandOneRow`) showing email/firstName/lastName/note/role/status; Add User dialog (email+password required); inline profile edit; password change; per-role toggle chips; lock/unlock toggle; delete-confirm dialog; sort/per-page in localStorage; sync button; `'agent'` role filtered out as service-only.
- **Password constants (from app.js):** `USER_PASSWORD_LENGTH_MIN 8` / `MAX 72`, `USER_PASSWORD_INVALID_RX /["'$&!]/`. System user ids: `SYSTEM_USER_ID 0000...0000`, `AGENT_USER_ID 0000...0001` (both → `i18n.systemUser` in `populateUserDetails`).
- **WebSocket/streaming:** none.

---

### 3.13 Clients (OAuth/API clients)

- **Route:** `/clients` (name `clients`)
- **File:** `html/js/routes/clients.js`
- **Purpose:** Admin management of OAuth/API clients (Hydra-backed). List, add (returns generated credentials once), edit, toggle per-resource/privilege permissions, regenerate secret, delete.

| HTTP | Path | Trigger | Request shape | Response shape |
|---|---|---|---|---|
| GET | `clients/` | `getClients()` in `loadData()` and after every mutation | — | `Array<Client{id,name,note,searchUsername,permissions[]}>`; **HTTP 400 → "check Hydra enabled" hint** |
| GET | `roles/permissions` | `loadData()` | — | permission catalog (resource/privilege definitions) |
| POST | `clients/` | `add()` (Add Client dialog; name required) | `{name,note}` | `new_client_credentials {clientId, secret,...}` shown once |
| PUT | `clients/{id}` | `update(client)` | `{name,note,searchUsername}` | updated client |
| POST | `clients/{id}/permission/{resource}/{privilege}` | `addPermission()` | empty body | ok |
| DELETE | `clients/{id}/permission/{resource}/{privilege}` | `removePermission()` | — | ok |
| PUT | `clients/{id}/secret` | `generateSecret(client)` | — | `new_client_credentials` shown in dialog |
| DELETE | `clients/{id}` | `removeClient(id)` (confirm) | — | ok (row spliced locally) |

- **Key interactions:** data table id/name/note with expandable rows; Add Client dialog → credentials dialog (shown once); permission matrix toggles; Generate Secret re-opens credentials dialog; delete-confirm; note truncation at 50 chars; sort/per-page in localStorage.
- **WebSocket/streaming:** none.

---

### 3.14 Config (Configuration / Settings tree)

- **Route:** `/config` (name `config`)
- **File:** `html/js/routes/config.js`
- **Purpose:** Grid-wide configuration editor. Hierarchical tree of settings (built from dotted ids), global and per-node (minion) values, advanced settings, custom UI-element editors (JSON array/object syntax), validation (regex/required), duplicate, reset-to-default, and Salt state syncs per changed module.

| HTTP | Path | Trigger | Request shape | Response shape |
|---|---|---|---|---|
| GET | `gridmembers/` | `loadData()` on mount/route update/advanced toggle | — | `Array<GridMember{id,name,role,status}>` (per-node value targets where `status==accepted`) |
| GET | `config/` | `loadData()` | query `{ advanced: bool }` | `Array<Setting{id,global,node,nodeId,title,description,value,default,defaultAvailable,readonly,sensitive,regex,multiline,syntax,uiElements,forcedType,options,required,...}>` (merged per id; per-node entries fold into a `nodeValues` map) |
| PUT | `config/` | `save(setting,nodeId)` — save global or per-node value | `{id, nodeId, value, file, syntax}` | ok; error body starting `ERROR_` surfaced verbatim |
| DELETE | `config/` | `confirmRemove()` — reset to default / remove per-node value | query `{ id, minion: nodeId }` | ok |
| PUT | `config/sync` | `sync()` — full grid sync | — | ok |
| PUT | `config/sync/{module}` | `syncModule(module)` — apply one Salt module | — | ok; `ERROR_SALT_ALREADY_RUNNING` → keep pending; 502–504 → "restarting" tip |

- **Key interactions:** treeview with search/filter, expand/collapse, advanced toggle (`?a=1`), deep-link via query params (`gridId, a, f, e, s`); per-setting editor (text/multiline/toggle/select/array); per-node value add (from grid members), reset, duplicate; Custom UI Elements (pack/unpack JSON, reorder, clear-entry confirm, dirty tracking, unsaved-changes discard dialog); after save/reset `notifyChangedSetting()` maps the id to Salt module(s) needing highstate; advanced flag in localStorage (`settings.config.advanced`).
- **WebSocket/streaming:** none observed.

---

### 3.15 Settings (User self-service account settings)

- **Route:** `/settings` (name `settings`)
- **File:** `html/js/routes/settings.js`
- **Purpose:** The logged-in user's own account/security settings, driven by a **Kratos self-service Settings flow**. Surfaces profile traits, password change, TOTP enroll/unlink (QR + secret), WebAuthn register/remove, and linked OIDC providers. Form submission posts to Kratos via an embedded auth UI URL; this Vue view only **reads** the flow and renders state.

| HTTP | Path | Trigger | Request shape | Response shape |
|---|---|---|---|---|
| GET | `settings/flows?id={authFlowId}` (via `$root.authApi` → Kratos) | `loadData()` on mount when an auth flow id exists | query `id` | Kratos `SettingsFlow {state, identity.traits{email,firstName,lastName,note}, ui.nodes[] (csrf_token, password group, totp_qr/totp_secret_key/totp_unlink, webauthn_register_*/webauthn_remove + webauthn_script, oidc group), ui.messages[]}` |

- **Key interactions:** if no auth flow id present → redirects (`location.pathname = settingsUrl`) to start a Kratos settings flow; renders tabs (profile/password/totp/webauthn/oidc), `?tab=` selects active tab; extracts csrf_token, identity traits, TOTP qr/secret/unlink, WebAuthn register trigger/displayname/key/script + existing keys, OIDC providers; injects the Kratos WebAuthn `<script>`; `runWebauthn()` evals the trigger onclick; flow messages → success `saveSuccess` tip / error `settingsInvalid` warning / `410` → reload flow; `resetDefaults()` clears localStorage UI prefs.
- **Note:** form POSTs (save profile, set password, TOTP, WebAuthn) are handled by the Kratos settings UI at `authSettingsUrl` (`$root.authUrl + 'settings' + location.search`), **not** an `/api` endpoint from this file. `410` on the flow → `reloadSettings()`.
- **WebSocket/streaming:** none.

---

### 3.16 Login

- **Route:** `/:pathMatch(.*)*` (catch-all; name `login`)
- **File:** `html/js/routes/login.js`
- **Purpose:** Login screen driven by a **Kratos self-service Login flow**. Reads the flow to determine available auth methods (password, TOTP, WebAuthn, OIDC), renders the banner/MOTD, handles error display, throttling countdown, and session-expiration modal. Credential submission posts to the Kratos login UI (`authLoginUrl`), **not** to `/api`.

| HTTP | Path | Trigger | Request shape | Response shape |
|---|---|---|---|---|
| GET | `/login/banner.md?v={ts}` (via `$root.createApi()`, raw relative / anonymous papi) | `loadData()` — render MOTD/banner | cache-buster `v=timestamp` | markdown text (rendered via `marked.parse`) |
| GET | `/auth/self-service/errors?id={id}` (via `$root.authApi` → Kratos) | `loadData()` when `?id=` present | query `id` | `{ error:{ status, reason } }` |
| GET | `/auth/self-service/login/flows?id={flow}` (via `$root.authApi` → Kratos) | `loadData()` | query `id=flow` | Kratos `LoginFlow {expires_at, ui:{ nodes:[{group,type,attributes:{name,value,...}}] (csrf_token, password/totp/webauthn/oidc, webauthn_login_trigger/webauthn_login/webauthn_script, identifier), messages:[{type,text}] }}`; **HTTP 410 → `document.location='/login'`** |
| POST | `/auth/self-service/login?flow={flow}` (**native HTML form submit**, handled by Kratos, **not** axios) | password/totp/webauthn submit | form-encoded `csrf_token, identifier, password, totp_code or webauthn_login` | Kratos session cookie + redirect (honors `AUTH_REDIRECT` cookie) |
| GET | `/auth/self-service/login/browser` (full-page redirect, `showLogin()`) | unauthenticated / no flow id / `checkForUnauthorized` trips | browser navigation (not XHR) | Kratos initializes flow, redirects back with `?flow=<id>` |

- **Key interactions:** on `created()` — if `?thr=` present → throttled countdown then re-login; if no `?flow=` → `showLogin()`; else show form, set `authLoginUrl = authUrl + 'login?flow=' + flowId`, run `loadData()`. Parses `ui.nodes`: csrf_token, password, totp (auto-focus `totp--0`; `submitTotp` injects code into hidden `#totp_code` and submits `#loginForm`), webauthn (inject script, `runWebauthn` evals onclick), oidc provider buttons. `checkSessionExpiration()` — if `expires_at` passed, show session-expired modal; else schedule a timer. Flow messages → `loginInvalid` warning; "email is already used" → `oidcEmailExists` warning.
- **WebSocket/streaming:** none.

---

### 3.17 Assistant (Onion AI chat)

- **Route:** `/assistant/:sessionId?` (name `assistant`)
- **File:** `html/js/routes/assistant.js`
- **Purpose:** Conversational AI assistant (licensed `'oai'`). **Streams** model responses over SSE, manages chat sessions/history, executes tools with per-tool approval (auto-approve for read-only tools), tracks token context length and credit balance, supports investigation-seeded sessions from alerts, context compression, model selection, session sharing, attach-to-case, and export. **This is the only streaming view.**

| HTTP | Path | Trigger | Request shape | Response shape |
|---|---|---|---|---|
| GET | `clientParameters 'assistant'` (via `$root.loadParameters('assistant', initAssistant)`) | `mounted()` — feature enablement, prompts, thresholds, models, adapters | — | `{enabled, investigationPrompt, compressContextPrompt, thresholdColorRatioLow/Med/Max, availableModels[{id,adapter,enabled,contextLimitSmall,contextLimitLarge,charsPerTokenEstimate,lowBalanceColorAlert}], availableAdapters[{name,...}]}` |
| GET | `/assistant/sessions` | `loadStoredChats()` — history list (initial + after each send/share) | — | `Array<Session{sessionId,title,createTime,tags[],userId}>` |
| GET | `/assistant/sessions/{sessionId}` | `loadChatFromBackend()`; `captureRawToolResult()` re-fetch | — | `{session{sessionId,userId,tags,createTime,deleteTime}, history:Array<{createTime,tags[],message{role,contentStr,contentBlocks[{type,text\|tool_use\|toolResult{content[{text,json}],isError,status,toolUseId}}],thoughts,usage{input_tokens,output_tokens,credits}}}>}` |
| GET | `/assistant/balance/{model}` | `loadCredits()` / `reloadCredits()` on init, after each streamed response, after tool execution | — | `{health_status:'healthy'\|..., credit_balance:number}` |
| POST | `/assistant/chat` (optional query `?entityType=alert_investigation&entityId={socId}`) | `callAIAPI()` from `sendMessage()` / `rejectTool()` / `compressCurrentSession()` — **STREAMING (SSE)** | `{msg, sessionId, model, tags}`; headers `Accept: text/event-stream`; `responseType: stream`; adapter `fetch` | SSE stream of Anthropic-style events (`message_start`, `content_block_start/delta/stop`, `message_delta`, `message_stop`, `error`); chunks `data: {json}` separated by `\n\n`, terminated by `[DONE]` |
| POST | `/assistant/tool/{toolName}` | `executeTool()` when a tool is approved/auto-approved and dequeued — **STREAMING (SSE)** | `ToolRequest {sessionId, toolUseId, params(=tool input), model, [auxData for query_cases = MRU cases]}` | SSE stream (same event types); `error` event → `assistantToolUseFail` |
| DELETE | `/assistant/sessions/{sessionId}` | `deleteChat(chatId)` | — | ok |
| PUT | `/assistant/sessions/{sessionId}` | `updateSessionTag()` / `toggleSharedSession()` | `{action:'add'\|'remove', tag}` | ok; error body `ERROR_SESSION_ATTACHED_TO_CASES{count}` handled |
| POST | `case/` | `createCase(title)` from `attachToCase()` (NEW case) | `{title, description}` | `{id,...}` new case id |
| POST | `/case/artifacts` | `attachToCase(sessionId,caseId)` — attach session as a case artifact | `{caseId, groupType:'attachments', artifactType:'assistant_chat', value:sessionId, description}` | ok |
| POST | `export` (via `$root.export`, server-side export) | `exportSession()` | `{type:'assistant_session', id:currentChatId}` | downloadable export |

- **Key interactions:** chat history sidebar (load/start/delete; titles from `session.title`; `restoreLastActive` optional); streaming chat with incremental text/thoughts + tool_use cards; tool approval flow (pending_approval cards with approve/reject; auto-approve for `query_events`/`get_playbooks`/`query_cases`/`query_detections` when `alwaysApproveReadRequests`; per-session tool queue runner); investigation sessions (`?investigation=true&socId=...` seeds `investigationPrompt`; first chat call adds the entity query params then strips them); context tracking vs model context limits (`increaseContextLimit` toggle, color thresholds, `compressCurrentSession`); credit-balance gating (blocks send if unhealthy/zero); model picker grouped by adapter; session share tag toggle; attach chat to existing/new case; export; choice-button markdown shortcuts (`[[CHOICE]]...`); many prefs + current chat id in localStorage (`settings.assistant.*`).
- **Streaming details:** `response.data` is a `ReadableStream` piped through `TextDecoderStream`; `processStreamingChunks` splits on `\n\n` and strips `data: `; `parseJsonChunk` handles concatenated/partial JSON across reads; `[DONE]` ends a message. Per-session streaming state (`activeStreamingSessionId`, `executingToolsBySession`, `toolQueues`, `toolRunnerBusy`) lets background sessions keep processing tool logic without updating the UI of a different open session. The backend persists messages automatically (no explicit save endpoint); `loadStoredChats` is re-called to refresh.

---

### 3.18 AI Metrics

- **Route:** `/aimetrics/:userId?/:sessionId?` (name `aimetrics`)
- **File:** `html/js/routes/aimetrics.js`
- **Purpose:** Admin analytics dashboard for assistant usage (licensed `'oai'`). Three drill-down levels via route params: per-user stats (no params), per-session for a user (`userId`), per-message for a session (`userId`+`sessionId`). Token/credit usage tables, pie/timeline charts, breadcrumb navigation, time-range + auto-refresh controls.

| HTTP | Path | Trigger | Request shape | Response shape |
|---|---|---|---|---|
| GET | `clientParameters 'assistant'` (via `$root.loadParameters('assistant', initAssistant)`) | `mounted()` — gate on `enabled` + `isLicensed('oai')` | — | `{enabled, ...}` |
| GET | `/assistant/admin/stats` | `loadData()` at Users level (no route params) | query `{format, range, zone}` | `Array<{userId, totalInputTokens, totalOutputTokens, totalCredits, totalSessions, totalMessages, modelUsage}>` |
| GET | `/assistant/admin/{userId}/sessions` | `loadData()` at Sessions level (`userId` in route) | query `{format, range, zone}` | `Array<Session{title,createTime,updateTime,kind,tags,usage{totalInputTokens,totalOutputTokens,totalCredits,totalMessages,modelUsage}}>` |
| GET | `/assistant/admin/{userId}/sessions/{sessionId}/history` | `loadData()` at Messages level (`userId`+`sessionId` in route) | query `{format, range, zone}` | `Array<{createTime, message{role, contentBlocks[], usage{input_tokens,output_tokens,credits}, model}}>` |
| GET | `users/{id}` (via `$root.getUserById`) | `lookupSocId()` — resolve each `userId` (UUID) to email at Users level | — | `User{email,...}` |

- **Key interactions:** Level 0 (Users) table + pie charts for credits/sessions/messages-by-model (resolves userId→email); Level 1 (Sessions) table with duration / credits-per-minute + timeline credits chart + models pie; Level 2 (Messages) table with role/tokens/credits/model + expandable rendered message (markdown + mermaid); breadcrumbs Users > Sessions > Messages + "open in assistant" link; relative/absolute time range (daterangepicker), timezone (`moment.tz`), auto-refresh timer; all persisted to localStorage (`settings.aimetrics.*`).
- **Note:** `range` built from `getStartDate()`/`getEndDate()` (`i18n.timePickerFormat`); `zone` from `moment.tz.guess()` or localStorage. Charts use `$root` chart helpers; `modelUsage` drives the per-model message-count pie.
- **WebSocket:** none.

---

### 3.19 Terms / License / License Key

- **Routes:** `/terms` (name `terms`), `/license` (name `terms-license`), `/licensekey` (name `terms-license-key`)
- **File:** `html/js/routes/terms.js`
- **Purpose:** Static terms-of-service / license display, and the admin license-key entry page (`/licensekey`, admin-gated in nav). The footer terms/license link is chosen by `licenseStatus`.
- **API calls:** **(unknown)** — no dedicated API calls were captured for these routes in the reconnaissance data. License/version data is sourced from the `/api/info` bootstrap (`license`, `licenseKey`, `licenseStatus`).

---

## 4. Consolidated API Endpoints Used by the UI

Backend wiring legend:
- **WIRED** — adapter wired and serving real data today (StaticKeyAuth, FileDatastore, StaticRBAC, Kratos/Stub users, InfoService).
- **needs-ES** — blocked on the Elasticsearch adapter currently being built.
- **needs-other** — blocked on a not-yet-wired Tier-2 adapter (cases, detections, assistant, config, clients, gridmembers, playbook, query).
- **Kratos** — handled by the Kratos auth service, not the SOC `/api`.
- **static** — web-root static asset, not `/api`.

| Endpoint (relative to `/api/` unless noted) | Methods | Views using it | Wiring |
|---|---|---|---|
| `info` | GET | GLOBAL (bootstrap), terms/license | **WIRED** |
| `users/`, `users/{id}` | GET, POST, PUT, DELETE | Users, Case (getActiveUsers), Aimetrics (getUserById), GLOBAL (getUserById/getUsers) | **WIRED** |
| `users/{id}/role/{role}` | POST, DELETE | Users | **WIRED** (users wired; role endpoints assume same adapter — verify) |
| `users/{id}/password`, `users/{id}/enable`, `users/{id}/disable`, `users/sync` | PUT | Users | **WIRED** (verify; depends on user adapter coverage) |
| `roles/` | GET | Users | **WIRED** (StaticRBAC) |
| `roles/permissions` | GET | Clients | **WIRED** (StaticRBAC; verify permission catalog) |
| `jobs` | GET | Jobs, Reports | **WIRED** (FileDatastore) |
| `job/`, `job/{id}` | GET, POST, DELETE | Jobs, Job, Case (analyze/export), Hunt (export), GLOBAL (export) | **WIRED** (FileDatastore) |
| `jobs/` (with kind=analyze) | GET | Case (analyze jobs) | **WIRED** (FileDatastore; analyze results may need analyzer backend) |
| `packets` | GET | Job | **WIRED** (FileDatastore) — verify packet source |
| `stream` (PCAP download href) | GET | Jobs, Job | **WIRED** (FileDatastore) — verify stream serving |
| `grid` | GET | Grid | **WIRED** (FileDatastore grid nodes) |
| `node` (WebSocket Kind) | WS push | Grid, Downloads | **WIRED** (node data; WS push delivery — verify) |
| `gridmembers/`, `gridmembers/{id}/add\|reject\|delete`, `gridmembers/{nodeName}/test\|restart\|import` | GET, POST | Gridmembers, Grid, Config | **needs-other** |
| `events/` | GET | Hunt/Alerts/Dashboards/Detections | **needs-ES** |
| `events/ack` | POST | Alerts (ack/escalate) | **needs-ES** |
| `query/filtered`, `query/grouped` | GET | Hunt family | **needs-ES** |
| `query/active`, `query/cancel/{taskId}` | GET, POST | Queries | **needs-other** |
| `case/`, `case/comments`, `case/artifacts[/attachments\|/evidence]`, `case/events`, `case/history` | GET, POST, PUT, DELETE | Case, Hunt (escalate→case), Assistant (attach) | **needs-other** |
| `detection/{id}`, `/detection`, `detection/{id}/history`, `detection/{detectId}/comment`, `detection/comment/{commentId}`, `detection/{engine}/genpublicid`, `/detection/{id}/duplicate`, `/detection/{detectId}/override/{index}/note`, `detection/convert`, `detection/public/{publicId}`, `detection/bulk/{action}`, `detection/sync/{engine}/{type}` | GET, POST, PUT, DELETE | Detection, Hunt (detections) | **needs-other** |
| `playbook/event/{socId}`, `playbook/detection/{publicId}` | GET | Hunt (alerts), Detection | **needs-other** |
| `config/`, `config/sync[/{module}]` | GET, PUT, DELETE | Config | **needs-other** |
| `clients/`, `clients/{id}[...]`, `clients/{id}/permission/{resource}/{privilege}`, `clients/{id}/secret` | GET, POST, PUT, DELETE | Clients | **needs-other** |
| `assistant/sessions[/{id}]`, `assistant/balance/{model}`, `assistant/chat`, `assistant/tool/{name}`, `assistant/admin/stats`, `assistant/admin/{userId}/sessions[/{sessionId}/history]` | GET, POST, PUT, DELETE | Assistant, Aimetrics | **needs-other** |
| `util/reverse-lookup` | PUT | GLOBAL (batchLookup), Case, Hunt, Job | **needs-other** (verify; util adapter) |
| `export` (assistant server-side export) | POST | Assistant | **needs-other** |
| WebSocket `ws` (`status`, `import`, `detection-sync`, `job`, `node`, `case`, `detections:bulkUpdate`, `related:bulkCreate`) | WS | GLOBAL, Hunt, Case, Job, Jobs, Grid, Downloads | **partial** — connection + `status`/`node`/`job` plausibly WIRED via FileDatastore/Info; `case`/`detection*` push needs-other |
| `motd.md` | GET | Home | **static** |
| `login/banner.md` | GET | Login, GLOBAL | **static** |
| `/auth/self-service/login/browser`, `login/flows`, `errors`, `login?flow=`, `logout/browser`, `settings/flows`, `settings/browser` | GET, POST | Login, Settings, GLOBAL (logout) | **Kratos** |

> Endpoints marked "verify" above are inferred from the FileDatastore/StaticRBAC wiring summary; confirm coverage against the actual route handlers before relying on them in tests. Anything not present in the reconnaissance data is **(unknown)** and must not be assumed.

---

## 5. Testability Notes

### Testable today (wired endpoints)

These views drive endpoints backed by wired adapters (`/api/info`, `/api/jobs`, `/api/job`, `/api/grid`, `/api/node`, `/api/roles`, `/api/users`):

- **Global shell / bootstrap** — `/api/info` hydrates version/license/parameters/user and sets `X-Srv-Token`; nav rendering, theme, snackbars, loading overlay, and the WebSocket connect/`status` indicator are all exercisable. Strong first target.
- **Jobs / Reports** (`/jobs`, `/reports`) — GET `jobs`, POST/DELETE `job/`. Note: report **creation** delegates to `$root.export` → POST `job/`.
- **Job detail** (`/job/:jobId`) — GET `job/`, GET `packets` (404 silently ignored when no packets yet), `stream` download hrefs.
- **Grid** (`/grid`) — GET `grid`; `node`/`status` WebSocket updates. (Member test/restart/import POST to `gridmembers` → **needs-other**.)
- **Users** (`/users`) — full CRUD against `users/` + `roles/` (verify the password/role/enable/disable/sync sub-endpoints are covered by the wired user adapter).
- **Home / Overview** (`/`) — static `motd.md`; no `/api` dependency.
- **Login / Settings** — Kratos flows; testable against a Kratos stub independent of the SOC `/api` adapters.

### Blocked on the Elasticsearch adapter (needs-ES)

- **Hunt / Alerts / Dashboards / Detections list** — the entire `events/`, `events/ack`, `query/filtered`, `query/grouped` surface. The shared `huntComponent` (5 routes) cannot return real results until the ES adapter lands. UI rendering / interaction tests can still run against mocked responses, but end-to-end search is blocked.

### Blocked on other Tier-2 adapters (needs-other)

- **Cases** (`/cases` list view shares huntComponent + needs-ES for events; `/case/:id` detail needs the case adapter), **Detection detail** (`/detection/*`), **Assistant** (`/assistant`, all streaming), **AI Metrics** (`/aimetrics`), **Config** (`/config`), **Clients** (`/clients`), **Grid Members** (`/gridmembers`), **Queries** (`/queries`), **Playbook** endpoints. These return no real data until their adapters are wired.

### One-origin and trailing-slash gotchas

1. **One origin is mandatory.** The frontend computes its API base as `location.origin + location.pathname + 'api/'`. There is no API-host config; tests must run frontend + backend on the **same origin** (dev launcher: `http://127.0.0.1:9822`, uvicorn serving `create_app` + static `html/`, anonymous auth `"*"`).
2. **Trailing-slash / catch-all StaticFiles gotcha.** A catch-all `StaticFiles('/')` mount swallows `/api/info` (the frontend omits the trailing slash) and returns 404. **Mount asset directories individually** so FastAPI's trailing-slash `307` redirect works for `/api/...` calls. This affects every `papi` request whose path lacks a trailing slash (`info`, `grid`, `jobs`, etc.).
3. **`X-Srv-Token` ordering.** `papi` requests after bootstrap carry `X-Srv-Token` (set only once `/api/info` succeeds). If the backend enforces it, tests must let `/info` complete first; if it does not yet enforce it, assertions on the header are still possible.
4. **`gridId` auto-injection.** Every `papi` request gets a `gridId` query param unless it equals `LOCAL_GRID_ID` (`''`); `info` and `reverse-lookup` force `LOCAL_GRID_ID`. Tests that match exact query strings must account for this.
5. **Session-expiry signal.** Any `text/html` response (or `401` on a non-`/api/` URL, or an `AUTH_REDIRECT` cookie) triggers a full-page redirect to Kratos `login/browser`. A misconfigured backend returning an HTML error page will navigate the test away from the SPA — assert on JSON error bodies instead.
6. **Hash routing.** All route navigation is under `#/...`; integration tests must drive and assert on the URL fragment, not the path.
7. **Background `/info` errors are silent.** Only the initial (non-background) `loadServerSettings` surfaces errors; connectivity issues otherwise appear only via the nav indicator (`connected` / `reconnecting`). The 502–504 path sets a **bare global** `reconnecting` variable (not `this.reconnecting`) — assert on the nav indicator, not component state.
