# Generate UI Integration Tests for the Security Onion Web Client

You are an autonomous engineer. Your job is to produce **end-to-end UI integration tests** that drive the **real Vue 3 web client** against the **real FastAPI backend**, both served on **one origin**, using a browser. This is the highest-fidelity test layer we have: it proves the shipped HTML/JS actually talks to the shipped API and renders real data.

Work methodically. Read first, run the app, observe reality, then write tests that encode what you observed. Do not invent endpoints, payloads, or selectors — verify them against the live app and the spec.

---

## 0. What this is and is NOT

- **IS:** Browser-driven integration tests. Launch the FastAPI app serving the static frontend, navigate the real UI in Chromium, assert the real `/api/*` network calls fire, assert the real DOM renders the response, exercise interactions, capture screenshots.
- **IS NOT:** Vue/jest unit tests. The repo already has those at `html/js/routes/**/*.test.js` (jest + `html/js/test_common.js`). **Do not touch, duplicate, or "port" them.** They mock the API; we are doing the opposite — no mocks, real backend.

**Guiding principle (hard rule):** *A blank frame, an uncaught console error, a failed `/api` request, or a missing expected DOM node = test FAILURE — even if the page "looks fine."* Assert positively (expected elements + expected data present) AND negatively (no console errors, no 4xx/5xx on expected calls).

---

## 1. First, read and observe (do this before writing any test)

1. **Read the authoritative spec:** `docs/web-client-spec.md`. It documents the architecture, global behavior (interceptors, `papi`/`authApi`, `/api/info` bootstrap, `X-Srv-Token` ordering, `gridId` auto-injection, hash routing), and a per-view section for all 18+ views with **API-call tables (method/path/trigger/request/response)** and key interactions. This is your source of truth for *what each view should do*. Trust it over your assumptions, but verify against the live app.
2. **Skim the frontend source** for the views you'll test: `html/js/app.js` (global construction, router, interceptors) and `html/js/routes/<view>.js`. Note in particular:
   - API base is computed as `location.origin + location.pathname + 'api/'` (see `app.js` ~line 220). **Same-origin is mandatory.** If the UI is not served from the same origin:port as the API, every call breaks.
   - Routing is **hash-based** (`VueRouter.createWebHashHistory()`, `app.js` ~line 189). Routes are registered per-view via `routes.push({ path: '/hunt', name: 'hunt', component })` at the bottom of each `html/js/routes/<view>.js`. So URLs look like `http://127.0.0.1:9822/#/jobs`, `…/#/grid`, `…/#/hunt`.
   - `papi` (the authenticated axios client) injects `X-Srv-Token` after the `/api/info` bootstrap and auto-injects `gridId` on many calls. Expect a `gridId` query param on most requests.
3. **Read the golden masters** in `backend/tests/characterization/golden_masters/` — these are captured real responses (`get_api_info.json`, `get_api_jobs__kind=.json`, `get_api_grid.json`, `get_api_users.json`, `get_api_roles.json`, `get_api_node.json`, plus ES-backed ones like `get_api_events__*.json`, `get_api_case.json`, etc.). Use them as the **expected response shape** to assert against, and later as ES seed fixtures.
4. **Run the app and click around manually first** (via the browser tool) so your tests encode observed reality, not guesses.

---

## 2. Environment & running the app (one origin, dev launcher)

The backend factory is `create_app()` in `backend/src/main.py`. It wires Tier-0/1 adapters and registers all `/api/*` routers, **but it does not yet mount the static frontend.** You must serve the frontend (`html/`) from the **same FastAPI app** so the client's same-origin API base resolves.

### 2.1 Commit a dev launcher (do this if one is absent)

Create `scripts/dev_launcher.py` (or `backend/src/dev_launcher.py`) that builds `create_app()`, mounts the static frontend, and runs uvicorn on `http://127.0.0.1:9822`. Critical detail below.

```python
# scripts/dev_launcher.py
"""Dev launcher: serve the real FastAPI app + real frontend on ONE origin.

    python scripts/dev_launcher.py
    -> http://127.0.0.1:9822  (UI at /, API at /api/*, anonymous auth)
"""
from pathlib import Path

import uvicorn
from fastapi.staticfiles import StaticFiles

from src.main import create_app  # run from backend/ so `src` is importable

HTML = Path(__file__).resolve().parents[1] / "html"  # adjust to repo layout


def build() -> "FastAPI":
    app = create_app()  # default AppConfig => anonymous_cidr 0.0.0.0/0 (auth "*")

    # GOTCHA: do NOT do app.mount("/", StaticFiles(directory=HTML, html=True)).
    # A catch-all "/" mount intercepts EVERYTHING, including /api/info — the
    # frontend requests "api/info" WITHOUT a trailing slash, so the catch-all
    # StaticFiles answers 404 instead of letting FastAPI's 307 trailing-slash
    # redirect reach /api/info/. Mount asset dirs INDIVIDUALLY and serve
    # index.html only for unmatched non-/api paths.
    app.mount("/js", StaticFiles(directory=HTML / "js"), name="js")
    app.mount("/css", StaticFiles(directory=HTML / "css"), name="css")
    app.mount("/images", StaticFiles(directory=HTML / "images"), name="images")
    app.mount("/login", StaticFiles(directory=HTML / "login", html=True), name="login")
    app.mount("/pages", StaticFiles(directory=HTML / "pages"), name="pages")

    from fastapi.responses import FileResponse
    from fastapi import Request

    @app.get("/")
    async def index():
        return FileResponse(HTML / "index.html")

    # SPA fallback for any other non-/api path (hash routing means most
    # navigation never hits the server, but a hard refresh on "/" must work).
    @app.get("/{path:path}")
    async def spa(path: str, request: Request):
        if path.startswith("api"):
            # let API 404s be real API 404s, not index.html
            return FileResponse(HTML / "index.html", status_code=404)
        return FileResponse(HTML / "index.html")

    return app


if __name__ == "__main__":
    uvicorn.run(build(), host="127.0.0.1", port=9822, log_level="info")
```

> If a launcher already exists in the repo, **use it** — verify it serves UI + API on the same origin and does NOT shadow `/api/info`. Only add one if missing. Confirm the trailing-slash behavior empirically: `curl -i http://127.0.0.1:9822/api/info` must reach the backend (200 or 307→200), **not** return the SPA index page.

### 2.2 Run it (background) and health-check before testing

```bash
# from repo root; adjust if your venv/runner differs
cd backend && PYTHONPATH=src python ../scripts/dev_launcher.py   # run in background
# health gate (poll until ok):
curl -fsS http://127.0.0.1:9822/api/health        # {"status":"ok"}
curl -fsS http://127.0.0.1:9822/api/info | head   # must be JSON, not HTML
curl -fsS http://127.0.0.1:9822/ | grep -i '<title' # the SPA shell
```

If `/api/info` returns HTML or 404, **stop and fix the static mount** before writing tests — every test depends on the bootstrap call.

### 2.3 Auth

- Local dev runs **anonymous auth**: `create_app()` defaults to `StaticKeyAuth(api_key="", anonymous_cidr="0.0.0.0/0")`, so requests from `127.0.0.1` are authorized as the wildcard user `"*"`. **No login is required.**
- The **Kratos login flow exists** (`html/login/`, `authApi` → `…/self-service/login`) but is **bypassed locally**. Do not test the login redirect in Phase 1; add a Kratos-backed login spec only when a Kratos instance is wired (Phase 2+), and mark it skipped until then.

---

## 3. Driver: Playwright (Chromium) via the Playwright MCP

Use the Playwright browser tools (`browser_navigate`, `browser_snapshot`, `browser_take_screenshot`, `browser_console_messages`, `browser_network_requests`, `browser_click`, `browser_type`, `browser_wait_for`, `browser_evaluate`). Capabilities you must use in every spec:

- **Navigate** to a hash route, e.g. `http://127.0.0.1:9822/#/jobs`.
- **Wait** for the view to settle (wait for an expected element or for the network to go idle) — never assert on a half-rendered frame.
- **Assert network:** read `browser_network_requests` and verify the expected `/api/...` calls fired with the correct **method**, **path**, **query params** (incl. `gridId`), and a **2xx** status. Flag any unexpected 4xx/5xx.
- **Assert DOM:** verify the shell elements render AND that **data from the response is visible** (e.g. a job ID from the `/api/jobs` payload appears in a table row).
- **Assert console:** `browser_console_messages` must contain **no errors** (and no unhandled rejections). Treat the spec's documented "silent background error / bare-global `reconnecting`" caveats as known-noise you may allowlist explicitly, but everything else is a failure.
- **Screenshot:** capture a full-page screenshot per view for the report.

You may alternatively codify these as runnable Playwright spec files (`@playwright/test`) if you set that up — but the MCP-driven flow is the baseline and must work. If you scaffold `@playwright/test`, keep it isolated from jest (separate config, separate dir) so the existing `html/js/**/*.test.js` jest suite is untouched.

---

## 4. Test organization & naming

- One spec file **per view**. Directory: `tests/ui-integration/`.
- Naming: `tests/ui-integration/<view>.ui.spec.(md|ts|js)` — e.g. `jobs.ui.spec.ts`, `grid.ui.spec.ts`, `overview.ui.spec.ts`.
- A shared helper module `tests/ui-integration/_helpers.*` for: base URL, navigate-and-wait, network-assert (`expectApiCall(method, pathRegex, {status, query})`), console-error gate, screenshot-to-report.
- A top-level `tests/ui-integration/README.md` describing how to launch the app and run the suite.
- If using the MCP-only flow (no `@playwright/test` runner), still create one `.md` per view documenting the exact navigate→assert steps you executed and their results, so the run is reproducible.

---

## 5. Per-view assertion CHECKLIST (apply to EVERY view)

For each view, drive it and assert ALL of the following. Pull the expected route, API calls, and interactions from the matching section of `docs/web-client-spec.md`.

1. **Shell renders:** the view's container/heading and primary layout elements are present (e.g. the data table, the toolbar, the filter bar). The app frame (nav drawer, top bar) is present and not blank.
2. **Expected API calls fire — correct method + path + params:** every call listed in the spec's API table for that view is observed in the network log with the right HTTP method, path, and query params (including the auto-injected `gridId` and, where relevant, `X-Srv-Token` header on `papi` calls). No expected call is missing; no expected call returns 4xx/5xx.
3. **Response data renders in the DOM:** at least one concrete field from the API response is asserted visible in the rendered DOM (e.g. a node ID from `/api/grid`, a username from `/api/users`). Cross-check shape against the relevant golden master.
4. **Key interactions work:** exercise the view's documented interactions — filters, tab switches, search/query submit, pagination/page-size, sort, row expansion, form submit, dialogs. After each interaction assert the resulting API call and/or DOM change.
5. **Empty / loading / error states:** confirm the loading indicator appears then clears; confirm the empty state renders sensibly when data is empty; where feasible, simulate an error (e.g. an endpoint that 404s today) and assert the UI shows an error/snackbar rather than a blank frame or a thrown exception.
6. **Console & accessibility:** zero console errors / unhandled rejections (minus the explicitly allowlisted spec caveats). Basic a11y sanity: the primary heading exists, interactive controls are reachable, no obviously broken ARIA. (Lighthouse/a11y deep-dive is optional, not required for pass.)

A view **passes** only when items 1–6 hold. Record any deviation as a bug (Section 8).

---

## 6. PRIORITIZATION — two phases

Wire status of the FastAPI rewrite (authoritative for prioritization):

- **WIRED today (serve real data):** `StaticKeyAuth` (auth), `FileDatastore` (jobs + grid nodes), `StaticRBAC` (roles), `Kratos/Stub` (users), `InfoService` (info). So these endpoints work **now**: `/api/info`, `/api/jobs`, `/api/job`, `/api/grid`, `/api/node`, `/api/roles`, `/api/users`.
- **NOT yet wired (need the Elasticsearch adapter under construction, or other Tier-2 adapters):** `/api/events` (hunt/alerts search), `/api/case*`, `/api/detection*`, `/api/assistant*`, `/api/config`, `/api/clients`, `/api/gridmembers`, `/api/playbook`, `/api/query`.

### Phase 1 — fully testable TODAY (do this first, make it green)

Write and pass these now. No external services required beyond the launcher.

| View / route | Backing endpoint(s) | Notes |
|---|---|---|
| **Overview / bootstrap** (`/api/info`, app shell, nav) | `GET /api/info` | The bootstrap call gates everything; assert `srvToken`, version, nav items, i18n strings present. |
| **Jobs** (`#/jobs`) | `GET /api/jobs?kind=…` | Table renders from `FileDatastore`; assert a seeded job appears; test the kind filter. |
| **Reports** (`#/reports`) | `GET /api/jobs?kind=…` | Same component family as Jobs; verify the report-kind variant. |
| **Job detail** (`#/job/<id>`) | `GET /api/job` | Navigate from a Jobs row or directly; assert detail fields render. |
| **Grid** (`#/grid`) | `GET /api/grid`, `GET /api/node` | Node list from `FileDatastore`; assert node IDs render; check refresh. |
| **Settings → Users** (`#/settings/...users`) | `GET /api/users` | From `Kratos/Stub` userstore; assert users render. |
| **Settings → Roles/RBAC** | `GET /api/roles`, `GET /api/roles/permissions` | From `StaticRBAC`; assert roles + permissions render. |

> Note: NodeService write paths are deferred (see `_NullStatusstore` / comments in `main.py`); only test **read** paths for grid/node in Phase 1.

### Phase 2 — ES-backed & other-adapter-blocked (gate + skip until ready)

Write the spec files now but **mark every test `skip` with a reason string** pointing at the missing adapter, so they're visible and turn on automatically once the dependency lands. Group:

- **ES-backed (need the Elasticsearch adapter + a seeded ES instance):** Hunt (`#/hunt`), Alerts (`#/alerts`), Dashboards, Detections (`#/detections`, `#/detection/<id>`), Cases (`#/cases`, `#/case/<id>`), Assistant (`#/assistant`), AI Metrics (`#/aimetrics`). Backed by `/api/events`, `/api/case*`, `/api/detection*`, `/api/assistant*`.
- **Other-adapter-blocked:** Config (`/api/config`), Clients (`/api/clients`), Grid Members (`/api/gridmembers`), Queries (`/api/query`), Downloads. Skip with the specific blocked endpoint named.

**Enabling Phase 2 (document this in the spec files):**
1. Stand up Elasticsearch (and any other Tier-2 dependency) and wire its adapter into `create_app()` / the launcher config.
2. **Seed ES from the golden masters:** the `backend/tests/characterization/golden_masters/get_api_events__*.json`, `get_api_case.json`, `get_api_detection*.json`, etc. capture the exact response shapes — derive index fixtures from them so the UI renders deterministic, asserted data. Provide a `scripts/seed_es.py` (or document the bulk-load) that loads these fixtures into the ES indices the adapter reads.
3. Flip the `skip` to active and run the same Section-5 checklist.

---

## 7. Test data seeding

- **Jobs (FileDatastore):** the launcher's `FileDatastore(job_dir=…)` reads JSON job files from a directory. Seed a known job into that dir (mirror the shape in `get_api_jobs__kind=.json` / `get_api_node.json`) so Jobs/Job/Grid have deterministic data to assert on. Document the exact dir and the seed file(s) used.
- **Users (Kratos/Stub):** default `StubUserstore` returns deterministic users — assert against what it returns (cross-check `get_api_users.json`).
- **Roles (StaticRBAC):** seed via the configured role/user files if `cfg.staticrbac.role_files` is set; otherwise assert the default. Cross-check `get_api_roles.json` / `get_api_roles_permissions.json`.
- **ES fixtures (Phase 2):** golden masters are the source of truth for expected shapes; use them both as seed input and as assertion references.
- **Golden masters as references:** for any view, diff the live `/api/<x>` response against `backend/tests/characterization/golden_masters/get_api_<x>*.json` to detect shape drift; assert the DOM against fields known to exist in that master.

---

## 8. OUTPUT — files, report, acceptance criteria

### Files to produce
- `scripts/dev_launcher.py` (if not already present).
- `tests/ui-integration/<view>.ui.spec.*` — one per view (Phase 1 active, Phase 2 skipped-with-reason).
- `tests/ui-integration/_helpers.*` and `tests/ui-integration/README.md`.
- Screenshots under `tests/ui-integration/__screenshots__/<view>.png`.

### Run report (write to `tests/ui-integration/RUN_REPORT.md`)
A structured report containing:
- A **pass/fail table per view** (view | route | phase | status | # api calls asserted | console errors | screenshot path).
- **Embedded/linked screenshots** per view.
- **Bugs filed:** for each failure, a concrete entry — view, repro steps (URL + interaction), expected vs actual, the offending request/response or console error, and a suggested root cause (e.g. "static mount shadows `/api/info`", "missing `gridId` param", "view renders blank because `papi` 401'd"). File real issues if an issue tracker is in use; otherwise list them in the report.
- A short **"how to run"** section.

### Acceptance criteria (the task is done when)
1. The dev launcher serves UI + API on `http://127.0.0.1:9822` one origin; `/api/info` is reachable (not shadowed); `/api/health` is 200.
2. **All Phase 1 view specs exist and PASS** the full Section-5 checklist against the real backend — real data rendered, expected `/api` calls asserted, zero unexpected console errors.
3. **All Phase 2 view specs exist**, each `skip`ped with a precise reason naming the blocking adapter, and each documenting how to enable it (ES seed from golden masters).
4. `RUN_REPORT.md` is complete with the pass/fail table, screenshots, and any bugs.
5. The existing jest unit suite (`html/js/routes/**/*.test.js`) is **untouched and still green**.
6. No mocks/stubs of the API in the integration layer — tests hit the live backend.

---

## 9. EXAMPLE skeletons (follow this pattern)

These illustrate the **navigate → wait → assert-network → assert-DOM → console → screenshot** flow. Adapt selectors/fields to what you observe in the live app and `docs/web-client-spec.md` (don't trust these literals blindly — verify).

### 9.1 Overview / bootstrap (`overview.ui.spec`)

```
GIVEN the dev launcher is up at http://127.0.0.1:9822
WHEN  I navigate to http://127.0.0.1:9822/
THEN  wait for the app shell (nav drawer + top bar) to render
ASSERT network:
  - GET /api/info  (note: no trailing slash from client; expect 200 or 307->200)
    -> 2xx, body has { srvToken, version, parameters/elasticVersion, ... }  (cf. get_api_info.json)
  - subsequent papi calls carry header X-Srv-Token == info.srvToken
ASSERT DOM:
  - the version string / grid name from /api/info is visible in the chrome
  - nav items render (Hunt, Jobs, Grid, ...), each linking to its #/route
ASSERT console: no errors (allowlist documented spec caveats only)
SCREENSHOT: __screenshots__/overview.png
```

Pseudo-Playwright:
```ts
await page.goto("http://127.0.0.1:9822/");
await page.waitForSelector("nav, .v-navigation-drawer"); // app shell
const info = reqs.find(r => /\/api\/info\/?(\?|$)/.test(r.url) && r.method === "GET");
expect(info, "GET /api/info must fire").toBeTruthy();
expect([200, 307]).toContain(info.status);
await expect(page.getByText(/grid|version/i)).toBeVisible(); // a field from the response
expect(consoleErrors, consoleErrors.join("\n")).toHaveLength(0);
await page.screenshot({ path: "tests/ui-integration/__screenshots__/overview.png", fullPage: true });
```

### 9.2 Jobs (`jobs.ui.spec`)

```
PRECONDITION: seed one known job into the FileDatastore job_dir (shape per get_api_jobs__kind=.json)
WHEN  I navigate to http://127.0.0.1:9822/#/jobs
THEN  wait for the jobs table to render
ASSERT network:
  - GET /api/jobs?kind=...&gridId=...  -> 200, array containing the seeded job
ASSERT DOM:
  - a table row shows the seeded job's id/status (a real field from the response)
INTERACTION:
  - change the "kind" filter -> assert a new GET /api/jobs?kind=<new> fires and the table updates
EMPTY/ERROR:
  - with an empty job_dir, assert the empty-state renders (no blank frame, no console error)
ASSERT console: no errors
SCREENSHOT: __screenshots__/jobs.png
```

Pseudo-Playwright:
```ts
await page.goto("http://127.0.0.1:9822/#/jobs");
await page.waitForSelector("table, .v-data-table");
const jobs = reqs.find(r => /\/api\/jobs\b/.test(r.url) && r.method === "GET");
expect(jobs?.status).toBe(200);
expect(new URL(jobs.url).searchParams.get("gridId"), "gridId auto-injected").toBeTruthy();
await expect(page.getByText(SEEDED_JOB_ID)).toBeVisible();
// interaction: filter
await page.getByRole("button", { name: /kind|filter/i }).click(); /* ...select kind... */
await page.waitForResponse(r => /\/api\/jobs\b/.test(r.url()));
expect(consoleErrors).toHaveLength(0);
await page.screenshot({ path: "tests/ui-integration/__screenshots__/jobs.png", fullPage: true });
```

### 9.3 Phase-2 skip pattern (e.g. `hunt.ui.spec`)

```ts
test.skip(
  "Hunt renders events from /api/events",
  // REASON: /api/events needs the Elasticsearch adapter (not wired yet).
  // ENABLE: stand up ES, wire adapter in create_app(), seed indices from
  //   backend/tests/characterization/golden_masters/get_api_events__*.json
  //   (see scripts/seed_es.py), then un-skip.
  async () => { /* full Section-5 checklist for #/hunt */ }
);
```

---

## 10. Workflow & discipline

- Get **the launcher + `/api/info` reachability** working first; nothing else matters until that's green.
- Write **one view spec at a time**, run it, make it pass, screenshot, then move on (small diffs, commit per view).
- Encode **observed** behavior — if the live app does something the spec didn't predict, note the discrepancy in `RUN_REPORT.md` (the spec flags some wirings as "verify" and some endpoints as "(unknown)" — your tests are how we resolve those).
- When done, re-run the whole Phase-1 suite from a cold start (launch → all specs) to prove reproducibility, confirm the jest unit suite still passes, and finalize `RUN_REPORT.md`.

Begin by reading `docs/web-client-spec.md`, then stand up the launcher and confirm `GET /api/info` returns JSON on one origin.
