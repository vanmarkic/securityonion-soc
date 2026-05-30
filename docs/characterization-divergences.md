# Characterization Replay — Known Divergences & Skips

`backend/tests/characterization/test_replay.py` replays golden masters captured
from the **Go reference server** (`localhost:9822`, 2026-05-28) against the
**wired FastAPI app** built by `create_app()` (anonymous auth + the file-backed
Tier-0/1 adapters). See `tests/characterization/conftest.py` for the wiring.

Status as of 2026-05-30: **17 passed, 8 skipped, 3 xfailed, 0 failed.**

The 7 fully-matching endpoints (`info`, `jobs`, `users`, `grid`, `gridmembers`,
`config`, `config?advanced=true`) match the Go reference on **both** status code
and response *shape* (field names + types), validating the rewrite's
serialization against the Go server.

## Documented divergences (xfail, non-strict)

These endpoints are wired, but their response diverges from the Go capture.
Recorded as `xfail` so replay stays green while the divergence stays visible; if
the rewrite is later aligned with Go, the test will `XPASS` and flag it.

| Endpoint | Go reference | Rewrite | Note |
|---|---|---|---|
| `GET /api/node` | `405` | `307` | FastAPI `redirect_slashes` redirects `/api/node` → `/api/node/`. Go returns 405 for the no-slash path. |
| `GET /api/roles` | `405` | `307` | Same trailing-slash redirect to `/api/roles/`. |
| `GET /api/roles/permissions` | `405` | `200` | The rewrite exposes a GET handler returning the permission map; the Go reference returned 405 (method not allowed) for this path. |

The two `307`s are a single root cause: FastAPI's default `redirect_slashes=True`
vs. the Go router's literal-path 405. Aligning would mean either disabling
`redirect_slashes` or registering the no-slash variants to return 405 — a
routing-parity decision deferred to a dedicated task (it affects every route,
including the currently-matching trailing-slash endpoints).

## Skipped endpoints (unwired adapters)

Skipped with a reason rather than failed, because the failure would be an
environment/wiring artifact, not a behavioral divergence.

| Endpoint | Reason |
|---|---|
| `GET /api/case/` | Elasticsearch casestore not wired (set `CHAR_ES_URL`) |
| `GET /api/events/` | Elasticsearch eventstore not wired (set `CHAR_ES_URL`) |
| `GET /api/query/active` | Elasticsearch eventstore not wired (set `CHAR_ES_URL`) |
| `GET /api/clients/` | no clientstore adapter implemented yet |

## Exercising the Elasticsearch-backed endpoints

The ES golden masters (`case`, `events`, `query/active`) skip unless a live
Elasticsearch is provided. To run them against the dev ES:

```bash
docker compose -f backend/docker-compose.dev.yml up -d elasticsearch
CHAR_ES_URL=http://localhost:9200 \
  backend/.venv/bin/python -m pytest backend/tests/characterization/test_replay.py -v
```

When `CHAR_ES_URL` is set, `conftest.py` wires the four ES stores into the
characterization app and stops skipping those endpoints. (Their golden statuses
are `405`/`400`, so they may surface as additional routing divergences — a
follow-up once ES is seeded with representative fixtures.)
