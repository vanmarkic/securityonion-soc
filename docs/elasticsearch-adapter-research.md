# Elasticsearch Adapter — Porting Research / Reference

Status: research / reference (no code committed yet)
Scope: port the Go `server/modules/elastic` module to a Python (FastAPI, async) adapter that satisfies the four storage ports already defined under `backend/src/ports/`.
Target reader: the engineer implementing `backend/src/adapters/elastic/`.

This document is a faithful capture of the Go behavior plus the concrete Python port contracts. Where the Go code has a latent bug or a load-bearing quirk, it is called out explicitly. Anything marked GOTCHA or VERBATIM must be reproduced exactly because a ported test asserts on it.

---

## 1. Overview

The Go `elastic` module is one module that constructs a shared Elasticsearch client and exposes **four** logical stores, all sharing the same `*elasticsearch.Client`:

| Go type | Python port (storage protocol) | Port file |
| --- | --- | --- |
| `ElasticEventstore` | `Eventstore` | `backend/src/ports/events.py` |
| `ElasticCasestore` | `Casestore` | `backend/src/ports/cases.py` |
| `ElasticDetectionstore` | `Detectionstore` | `backend/src/ports/detections.py` |
| `ElasticAssistantstore` | `Assistantstore` | `backend/src/ports/assistant.py` |

All four storage protocols are `@runtime_checkable` and every method is `async`. The Python ES adapter implements these four storage protocols only. `DetectionEngine` and `AssistantManager` live in the same port files but are **behavioral/AI ports, not storage** — the ES adapter does not implement them.

Two cross-cutting concerns sit underneath all four stores:

1. **Shared ES client + transport** (`elastic.go`, `elasticeventstore.go`, `elastictransport.go`): client construction, TLS verify, timeouts, run-as header injection, the primary-vs-remote client list used for update fan-out.
2. **The converter** (`converter.go`): a PURE, synchronous translation layer between the SOC query language (a parsed Lucene-ish AST) and Elasticsearch DSL, plus the reverse mapping of ES responses into domain models. This is the single most important and most testable piece. It must be ported first and exactly — ported tests assert byte-level JSON shapes.

Go files in scope:

```
server/modules/elastic/elastic.go               # module init/config + route registration
server/modules/elastic/elasticeventstore.go     # client list, Search/MSearch/Scroll/Update/Index/Delete/Ack/Tasks/PopulateJob
server/modules/elastic/elastictransport.go       # http transport, run-as header
server/modules/elastic/elasticqueries.go         # ack/investigate painless script builders, tasks parsing
server/modules/elastic/converter.go              # PURE query<->DSL + response->domain mapping
server/modules/elastic/elasticcasestore.go       # cases/comments/related/artifacts/streams + audit
server/modules/elastic/observables.go            # observable type classifier
server/modules/elastic/elasticdetectionstore.go  # detections/comments + bulk + template check
server/modules/elastic/joblookuphandler.go       # PCAP pivot HTTP handler (separate concern)
server/modules/elastic/template.go               # index-template existence helper
model/event.go model/querytask.go model/query.go model/case.go model/detection.go model/assistant.go
util/dates.go util/strings.go
```

Recommended client library: the official `elasticsearch` Python package's `AsyncElasticsearch`. The converter/mapping logic must stay independent of the client so it can be unit-tested with JSON fixtures and a mocked client.

---

## 2. ES Client & Configuration

### 2.1 Config keys + defaults (`Elastic.Init`)

`Elastic.Init` reads all config keys, coerces defaults, then constructs `ElasticEventstore` and conditionally the three sub-stores. In Python this maps to a Pydantic settings model (snake_case) consumed by an adapter factory.

Eventstore config keys (Go default -> Python field):

| Go key | Default | Python (snake_case) | Notes |
| --- | --- | --- | --- |
| `hostUrl` | `elasticsearch` | `host_url` | primary host |
| `remoteHostUrls` | `[]` | `remote_host_urls` | remote cluster clients |
| `extractCommonObservables` | `[]` | `extract_common_observables` | passed to casestore |
| `verifyCert` | `true` | `verify_cert` | **maps to `verify_certs` (see GOTCHA)** |
| `username` | `''` | `username` | |
| `password` | `''` | `password` | |
| `timeShiftMs` | `120000` | `time_shift_ms` | PCAP filter padding |
| `defaultDurationMs` | `1800000` | `default_duration_ms` | |
| `esSearchOffsetMs` | `1800000` | `es_search_offset_ms` | PCAP range half-width |
| `timeoutMs` | `300000` (0 -> 300000) | `timeout_ms` | request timeout; 0 coerced |
| `cacheMs` | `86400000` | `cache_ms` | field-caps cache TTL (24h) |
| `index` | `*:so-*` | `index` | comma-list of read indices |
| `asyncThreshold` | `10` | `async_threshold` | ack async cutoff |
| `intervals` | `25` | `intervals` | timeline bucket count |
| `maxLogLength` | `1024` | `max_log_length` | log truncation |
| `casesEnabled` | `true` | `cases_enabled` | |
| `lookupTunnelParent` | `true` | `lookup_tunnel_parent` | |
| `detectionsEnabled` | `true` | `detections_enabled` | |
| `assistantEnabled` | `true` | `assistant_enabled` | |
| `maxScrollSize` | `10000` | `max_scroll_size` | scroll page size |

Sub-store config:

| Go key | Default | Used by |
| --- | --- | --- |
| `caseIndex` | `*:so-case` | casestore |
| `auditIndex` | `*:so-casehistory` | casestore |
| `maxCaseAssociations` | `1000` | casestore |
| `schemaPrefix` | `so_` | all stores |
| `detectionIndex` | `*:so-detection` | detectionstore |
| `detectionAuditIndex` | `*:so-detectionhistory` | detectionstore |
| `maxDetectionAssociations` | `1000` | detectionstore |
| `assistantChatIndex` | `*:so-assistant-chat` | assistantstore |
| `assistantSessionIndex` | `*:so-assistant-session` | assistantstore |
| `bulkIndexerWorkerCount` | `-1` (<=0 -> CPU count) | casestore/detectionstore |

`Elastic.Init` also calls `licensing.ValidateDataUrl(host)` and registers Chi routes `/joblookup` and `/api/joblookup`. In Python the route registration becomes a FastAPI route (see §4.6, joblookup). Licensing flags (`FEAT_RPT`, `FEAT_TTR`) become injected config booleans.

### 2.2 Client list (`ElasticEventstore.Init`)

- Build the **primary** client from `hostUrl`. On success it is the first element of `esAllClients` and the only element of `esClient` (primary).
- For each remote host build a client; on success append to `esAllClients` and `esRemoteClients`; **on the first failure, break the loop** (remaining remotes silently skipped). Only the primary client's construction error is returned.
- `timeoutMs`/`cacheMs` are stored as durations.

Client routing (critical):

| Operation | Clients used |
| --- | --- |
| Search / MSearch / Scroll / Index / Delete / FieldCaps / Tasks | **primary only** |
| Update / Acknowledge (update_by_query) | **all clients (fan-out)** — partial success tolerated |

Python: keep `self._primary` and `self._all_clients: list[AsyncElasticsearch]`.

### 2.3 `makeEsClient` / transport (`elastictransport.go`)

Go builds `elasticsearch.Config{Addresses:[host], Username, Password, Transport: NewElasticTransport(...)}`. Transport details:

- `MaxIdleConnsPerHost=10`, `ResponseHeaderTimeout=timeoutMs`, dial timeout `=timeoutMs`.
- `TLSClientConfig.InsecureSkipVerify = !verifyCert`.
- **If BOTH `user` and `pass` are non-empty**, wrap the transport so every `RoundTrip` injects header `es-security-runas-user = <run-as username from context>` when present (Elastic security run-as impersonation). If user/pass empty, no run-as wrapper.
- Logs masked password (`*****` if non-empty, else empty).

Python mapping:

```python
AsyncElasticsearch(
    hosts=[host],
    basic_auth=(user, pass_) if (user and pass_) else None,
    verify_certs=verify_cert,          # NOTE: NOT inverted (see GOTCHA below)
    ssl_show_warn=False,
    request_timeout=timeout_ms / 1000,
)
```

GOTCHA — TLS verify polarity: Go config `verifyCert=true` means "verify". Go sets `InsecureSkipVerify = !verifyCert`. The Python client uses `verify_certs` directly (true = verify), so map `verify_certs = verify_cert` (do NOT invert). The inversion only existed because Go's flag was named for the negative.

GOTCHA — run-as header: when basic auth is configured, every request can carry `es-security-runas-user: <username>` derived from the authenticated request context. If the deployment relies on Elastic-side per-user authorization, the Python port must inject this header per request. Implement via a per-request `client.options(headers={"es-security-runas-user": run_as})` derived from a `contextvar` (request_id / requestor_id / run_as). If not relying on Elastic run-as, document the deviation explicitly.

### 2.4 Index resolution helpers

- `transformIndex(index)`: replace `{today}` with local-date `YYYY.MM.DD`. Applied on index/delete only.
- `disableCrossClusterIndex(index)`: split on the first `:` and keep the part after it (`*:so-*` -> `so-*`). Applied for **writes** (index, delete, update fan-out, audit), NOT for reads (search/scroll/field-caps keep the cross-cluster pattern). Python: `index.split(":", 1)[-1]`.
- Cross-cluster prefix stripping for update is necessary because `_update_by_query` cannot target remote clusters; each remote client updates its LOCAL indices.

---

## 3. The Converter (most important)

`converter.go` is **pure and synchronous**. Keep it pure and sync in Python. Only adapter methods that call ES become `async`. Suggested module: `backend/src/adapters/elastic/converter.py`.

Reuse `server/modules/elastic/converter_response.json` and `converter_response_failure.json` verbatim as pytest fixtures under `backend/tests/fixtures/`.

GOTCHA — key ordering: Go's `json.WriteJson` sorts map keys alphabetically. Ported tests compare exact JSON strings, so serialize builder output with `json.dumps(obj, sort_keys=True)` when byte-equality matters. Builders should return dicts; serialize at the HTTP/test boundary.

### 3.1 Function-name map (Go -> Python)

| Go | Python (suggested) | Purpose |
| --- | --- | --- |
| `makeQuery` | `make_query` | bool query body |
| `makeAggregation` | `make_aggregation` | nested terms agg |
| `makeTimeline` | `make_timeline` | date_histogram |
| `calcTimelineInterval` | `calc_timeline_interval` | bucket-size ladder |
| `formatSearch` | `format_search` | empty -> `*` |
| `mapSearch` | `map_search` | `field:` -> `field.keyword:` |
| `stripSegmentOptions` | `strip_segment_options` | drop `-` flags |
| `mapElasticField` / `unmapElasticField` | `map_elastic_field` / `unmap_elastic_field` | .keyword remap/unremap |
| `flatten` / `flattenKeyValue` | `flatten` | nested _source -> dotted |
| `parseAggregation` | `parse_aggregation` | buckets -> EventMetric |
| `convertToElasticRequest` | `build_search_request` | search body |
| `convertToElasticMSearchRequest` | `build_msearch_request` | msearch sub-body |
| `convertToElasticScrollRequest` | `build_scroll_request` | scroll body |
| `convertToElasticUpdateRequest` | `build_update_request` | update_by_query body |
| `convertToElasticIndexRequest` | `build_index_request` | json passthrough |
| `convertFromElasticResults` | `parse_search_results` | response -> EventSearchResults |
| `convertFromElasticScrollResults` | `parse_scroll_results` | page -> EventScrollResults |
| `convertFromElasticMSearchResults` | `parse_msearch_results` | msearch -> results |
| `convertFromElasticUpdateResults` | `parse_update_results` | update_by_query -> results |
| `convertFromElasticIndexResults` | `parse_index_results` | index/delete -> IndexResults |
| `ConvertObjectToDocumentMap` | `convert_object_to_document_map` | wrap object for indexing |

### 3.2 SOC query -> ES DSL rules (exhaustive)

The query string is parsed (`Query.parse`, already ported to `backend/src/domain/query.py`) into pipe-separated segments. First segment = `search`; subsequent typed by leading keyword (`groupby`, `sortby`, `table`). The converter consumes `Query.segments`.

**(1) `make_query` (bool query):**

```json
{"bool": {
  "must": [
    {"query_string": {"query": "<lucene or '*'>", "analyze_wildcard": true, "default_field": "*"}}
    /* , {"range": {"@timestamp": {"gte": "<RFC3339>", "lte": "<RFC3339>", "format": "strict_date_optional_time"}}}  ONLY when end_time is non-zero */
  ],
  "filter": [], "should": [], "must_not": []
}}
```

- The search segment is field-remapped via `map_search`, reserialized via `Segment.__str__`, then `format_search` (empty/whitespace -> `*`).
- `filter`/`should`/`must_not` are ALWAYS emitted as empty arrays. The converter never populates them — all AND/OR/NOT logic lives inside the `query_string` text. Do NOT optimize these away; tests assert their presence.
- Range clause is added to `must` only when `end_time` is non-zero/None. MSearch passes zero times -> no range.
- Times are already in requestor TZ (via `populate`/`ParseDateRange`) and serialized RFC3339 (offset preserved).

**(2) `format_search`:** `strings.Trim(input, " ")` then empty -> `*`. Trims only the space char (not all whitespace) and does NOT touch backslashes. Python: `input.strip(" ") or "*"`.

**(3) `map_search`:** for each term whose `Raw` ends with `:` AND is not grouped AND not quoted, strip `:`, run `map_elastic_field`; if changed, set `term.Raw = mapped + ":"`. The search serialization inserts a SPACE after the colon (`foo: "bar"`) because the parser tokenizes `foo:` and the value separately. Backslashes/quotes are escaped by the segment serializer (`\` -> `\\`, `"` -> `\"`).

**(4) `map_elastic_field` / `unmap_elastic_field`** (live in eventstore, used by converter):
- `map_elastic_field(field)`: if `field` is defined and NOT aggregatable, try `field + ".keyword"`; if that exists and IS aggregatable, return the `.keyword` variant; else unchanged. Used in aggregations, `map_search`, scroll URL sort.
- `unmap_elastic_field(field)`: if `field` ends with `.keyword` and the base is defined and NOT aggregatable, strip `.keyword`; else unchanged. Used in `flatten` when building payload.
- Tested behavior: `smb.service` -> `smb.service.keyword`; `agent.ip` stays (already aggregatable); `event.acknowledged` stays (no keyword); `event.module/category/.../timezone` -> `.keyword`.

**(5) Aggregations (only when `metric_limit > 0`):**
- `timeline` (only when `end_time` non-zero): `{"date_histogram": {"field": "@timestamp", "fixed_interval": <calc_timeline_interval>, "min_doc_count": 1}}`.
- For each groupby segment (ordered, prefix `groupby_<idx>`): `fields = strip_segment_options(raw_fields())`; if non-empty, `(agg, name) = make_aggregation(field_defs, prefix, fields, metric_limit, ascending=false)`; `aggregations[name] = agg`.
- A single `bottom` agg added ONCE (on the first groupby's first field only, ascending) for least-common values.

`make_aggregation` (recursive, CRITICAL ordering):
1. `order = {"_count": "desc" or "asc"}`.
2. If `keys[0]` ends with `*`: strip the trailing `*` (Go MUTATES the slice) AND set `agg_fields["missing"] = "__missing__"`. **Star detection/strip happens BEFORE `map_elastic_field`.**
3. `agg_fields["field"] = map_elastic_field(keys[0])`, `["size"] = count`, `["order"] = order`; `agg["terms"] = agg_fields`.
4. `name = prefix + "|" + keys[0]` (after star strip).
5. If `len(keys) > 1`, recurse on `keys[1:]` with `prefix = name`, place under `agg["aggs"] = {inner_name: inner_agg}`.
- Returns `(agg, name)`. Compound names joined by `|`, e.g. `groupby_0|source_ip|destination_ip`. The response parser keys on the `groupby_` prefix and on the `|` separator — preserve exactly.
- GOTCHA: Go mutates `keys` in place; `bottom` is built from `fields[0:1]` AFTER `make_aggregation` ran, so the `*` is already stripped. In Python, strip `*` before building both (or pass copies) but ensure the resulting agg names contain no `*`.

**(6) `calc_timeline_interval` (port the ladder EXACTLY):**
`interval_seconds = (end - begin).total_seconds() / intervals`, then ascending `<=` (inclusive, seconds):

```
<=3   -> 1s     <=7   -> 5s     <=13  -> 10s    <=23  -> 15s
<=45  -> 30s    <=180 -> 1m     <=420 -> 5m     <=780 -> 10m
<=1380-> 15m    <=2700-> 30m    <=5400-> 1h     <=25200-> 5h
<=54000-> 10h   <=259200-> 1d   <=604800-> 5d   <=1296000-> 10d
else  -> 30d
```

`intervals` default 25. Examples: 8h/25 -> `15m`; 1s/25 -> `1s`; ~31yr/25 -> `30d`. An off-by-one on a boundary changes the bucket.

**(7) Sort — TWO shapes:**
- If a `sortby` segment is present, it WINS (ignores `criteria.sort_fields`): build an ARRAY of `{field: {order, missing: "_last", unmapped_type: "date"}}`; trailing `^` on a field => `asc` (strip the `^`) else `desc`.
- Else fall back to `criteria.sort_fields` -> simple MAP `{field: order}`.

**(8) `search_after`:** passthrough of `criteria.search_after` when non-empty (paired with `EventRecord.sort` on the way out for cursor pagination).

**(9) size:** `event_limit` (search, default 25) / `max_scroll_size` (scroll, default 10000). Update and msearch bodies have no `size` (msearch sub-body has neither size/aggs/sort). `metric_limit` default 10 — an empty criteria still builds aggregations unless `metric_limit` is explicitly 0.

Empty search body (metric_limit=0):
```json
{"query":{"bool":{"filter":[],"must":[{"query_string":{"analyze_wildcard":true,"default_field":"*","query":"*"}}],"must_not":[],"should":[]}},"size":25}
```

**Update body:** `{"query": <make_query>, "script": {"source": "<scripts joined '; '>", "lang": "painless", "params": <criteria.params if non-empty>}}`. No aggs/size/sort.

### 3.3 ES response -> domain mapping

`parse_search_results` (and scroll/msearch variants):

- VALIDATION sentinels: search/scroll require `took` + `timed_out` + `hits` present, else error `Elasticsearch response is not a valid JSON search result`. Update requires `took` + `timed_out` + `updated` + `noops`, else `Elasticsearch response is not a valid JSON updated result`.
- `elapsed_ms = int(took)` (truncate toward zero).
- `timed_out == true` -> error `Timeout while fetching results from Elasticsearch` (update: `Timeout while updating documents in Elasticsearch`).
- `hits.total` has TWO shapes: a bare number (older ES / fixture uses `"total": 23689430`) OR an object `{value, relation}`. Handle both. `total_events = int(that)`.
- Per hit -> `EventRecord`: `source = _index`, `id = _id`, `type = _type?`, `score = _score?`, `payload = flatten(_source)`, `sort = hit.sort?`. `time` parsed from payload `@timestamp` else `timestamp` (RFC3339); `timestamp` formatted to ms-precision UTC literal-Z (Go layout `2006-01-02T15:04:05.000Z`). Fallback chain: `@timestamp` -> `timestamp` -> zero (`0001-01-01T00:00:00.000Z`). Example normalization: `2020-04-24T03:00:55.3Z` -> `2020-04-24T03:00:55.300Z`. Python emit: `f"{dt:%Y-%m-%dT%H:%M:%S}.{dt.microsecond // 1000:03d}Z"`.
- Aggregations (search only, not scroll/msearch sub): for each top-level agg call `parse_aggregation(name, obj, [], results)` populating `results.metrics: dict[str, list[EventMetric]]`.
- `_shards.failed > 0`: iterate failures, log `reason.type` / `reason.reason` (default `N/A`), set error `ERROR_QUERY_FAILED_ELASTICSEARCH` BUT keep already-parsed events/metrics (non-fatal). Failure JSON may have null node/type/reason.

`parse_aggregation` (recursive):
- Read `agg["buckets"]`; if missing return.
- Per bucket: `doc_count` (skip if missing) -> `EventMetric.value`; key = `bucket["key_as_string"]` ?? `bucket["key"]` (prefer `key_as_string`; date_histogram buckets carry ISO timestamps); skip if no key; copy parent keys, append this key -> `metric.keys`; append.
- Recurse only into sub-aggs whose NAME starts with `groupby_` (so `timeline` and `bottom` are parsed only at top level, never recursed). Value is a float.

`flatten` / `flatten_key_value`: nested `_source` -> dotted keys (`{a:{b:1}}` -> `{"a.b": 1}`). Only maps are recursed; arrays/scalars are leaves. Each leaf key passes through `unmap_elastic_field` (strip `.keyword` when base non-aggregatable).

`parse_msearch_results`:
- `result.elapsed_ms = took` (top-level overall elapsed).
- `responses[i]` aligned positionally to sub-queries. If a response has an `error` key -> raise with `error.reason` (fallback raw error) and abort the whole parse. Else `parse_search_results` into a sub `EventSearchResults` (its own `took` -> that response's `elapsed_ms`); append.

`parse_index_results` (also reused for DELETE responses): `document_id = _id`, `success = result in {"created", "updated"}`. DELETE result `deleted` -> `success = False`. No nil-guards in Go; Python should use `.get` and tolerate missing keys.

### 3.4 Domain converters (cases/detections — see §4.3 / §4.4)

`converter.go` also holds `convert_elastic_event_to_object` (polymorphic dispatch on `payload[prefix + "kind"]`) and per-kind converters (case/comment/detectioncomment/related/artifact/artifactstream/detection). Key behaviors:
- `convert_severity(sev)`: lowercase; `1->low 2->medium 3->high 4->critical`; other non-empty passes through lowercased; empty -> `high`. **MUTATES** the case severity on read and during validation.
- `parse_time(map, key)`: accepts datetime / RFC3339 string; anything else -> zero. Document the None-vs-epoch-zero convention.
- `convert_to_string_array`: maps each element via string cast (Go panics on non-string). Python: tolerate or mirror.
- Dispatch: missing `kind` key -> error `Unknown object kind; id=<id>`; present-but-unrecognized kind -> `(None, None)`.
- Override mapping (`convert_elastic_event_to_override`): pointer fields set only when present AND non-null; `count`/`seconds` int from float.

NEST-ON-WRITE vs FLATTEN-ON-READ asymmetry (the single biggest mapping gotcha for cases/detections): documents are written nested under `so_<kind>` but read back FLATTENED into dotted keys (`so_case.title`, `so_detection.publicId`) — EXCEPT `overrides`, which come back as nested objects. Confirm how the ported eventstore returns `_source` before mirroring.

---

## 4. Per-store method maps

Notation: ES API names are the `AsyncElasticsearch` method. "AuthZ (op,target)" replaces Go's `server.CheckAuthorized(ctx, op, target)` — port as a FastAPI auth dependency/guard raising 403 with the operation/target preserved.

### 4.1 Eventstore (`ElasticEventstore`)

| Go method | Python port method | ES API | Index | Behavior / gotchas |
| --- | --- | --- | --- | --- |
| `Search` | `search(criteria) -> EventSearchResults` | `es.search` | `index` (comma-split) | AuthZ(read,events). refresh_cache -> `build_search_request` -> `es.search(index=..., body=query, track_total_hits=True, ignore_unavailable=True)` -> `parse_search_results`; set `results.criteria`; `complete()`. Single round-trip, no scroll. |
| `MSearch` | (not on storage Protocol; keep internal) | `es.msearch` | per-criteria `index` | AuthZ(read,events). NDJSON: header `{"index": criteria.index}` then `build_msearch_request` (no range). Lines `\r\n`-separated, trailing `\n`. Index value JSON-encoded into header (escaped, not interpolated). `parse_msearch_results`. |
| `Scroll` | (not on storage Protocol; used by detection scroll) | `es.search(scroll='1m')` + `es.scroll` + `es.clear_scroll` | explicit `indexes` else `index` | NO auth check (caller-gated). `build_scroll_request` (size=max_scroll_size). Initial search with `scroll='1m'`, `track_total_hits=True`, `ignore_unavailable=True`, plus URL sort built from `sort_fields` via `map_elastic_field` as `field:order`. Loop while `last_page_count > 0` AND `len(events) < total_events`: `es.scroll(scroll_id=..., scroll='1m')`; accumulate events + elapsed_ms. After loop, if scroll_id set, `es.clear_scroll(scroll_id=...)`; **404 must be ignored (warn-only, not error)**. Keep-alive hardcoded 60s. Mid-scroll errors return partial events + error. Special log: 0 events + query contains `so_detection.engine` -> "scrolled for 0 results". |
| `Update` | (internal; used by acknowledge + cases/detections) | `es.update_by_query` | `disableCrossClusterIndex(split(index))` | AuthZ(write,events). refresh_cache. `build_update_request`. **FAN-OUT over all clients**: per client `es.update_by_query(index=..., body=..., conflicts='proceed', refresh=True, wait_for_completion=not criteria.asynchronous)`. Sync+no-err -> `parse_update_results` + accumulate. Per-client errors collected in `results.errors`. **Partial success: if at least one host succeeded, overall error reset to None.** Async returns task handle (not parsed). `complete()`. |
| `Index` | (internal) | `es.index` | caller index (cross-cluster stripped, `{today}` transformed) | If id given, `validate_id`. AuthZ(write,events). refresh_cache. `es.index(index=transform_index(index), id=id or None, document=document, refresh=True)`. `parse_index_results`. |
| `Delete` | (internal) | `es.delete` | caller index (stripped/transformed) | `validate_id(id)` (required). AuthZ(write,events). `es.delete(index=transform_index(index), id=id)`. No refresh flag. |
| `Acknowledge` | `acknowledge(criteria: EventAckCriteria) -> EventUpdateResults` | `es.update_by_query` (via Update) | `index` | See §4.1.1. |
| `GetActiveQueries` | `get_active_queries(filter_internal: bool) -> list[QueryTask]` | `es.tasks.list` | cluster tasks | AuthZ(read,queries). Iterate all clients (see BUG note); `parse_tasks(body, client, grid_id='', filter)`. `filter=true` excludes non-cancelable/persistent/child/list-self tasks. |
| `CancelQuery` | `cancel_query(query_id: str) -> None` | `es.tasks.cancel` | cluster tasks | AuthZ(delete,queries). Find task whose `task_id == query_id` (via `get_active_queries(False)`), then call `client_for_task.tasks.cancel(task_id=query_id)`. None match -> error `query not found`. |
| `PopulateJobFromDocQuery` | separate (joblookup) | `es.search` (multiple) | `index` | PCAP pivot, see §4.6. |
| `refreshCache` / field-caps | `_refresh_cache` (asyncio.Lock + TTL) | `es.field_caps(fields='*')` | `index` | See §4.1.2. |

`QueryTask` is a plain class already defined in `events.py` (`to_dict` keys: gridId, taskId, details, startTime, elapsedMs, cancelable). `get_active_queries` MUST return `list[QueryTask]` instances.

`EventsService` is a thin passthrough: `search` and `acknowledge` are called by it; `get_active_queries`/`cancel_query` are NOT called by `EventsService` but ARE part of the Protocol (called by handler/job layer) — implement them regardless.

#### 4.1.1 Acknowledge details

- Require `len(event_filter) > 0` else error `EventFilter must be specified to ack an event`.
- AuthZ(ack,events). Build an `EventUpdateCriteria` with `user_id` from the requestor context.
- `add_ack_escalate_update_scripts(criteria, now, acknowledge, escalate, user_id)` (dispatcher).
- `populate(search_filter, date_range, date_range_format, timezone, metric_limit='0', event_limit='0')`. Pull the `search` named segment from parsed query (or empty).
- For each `event_filter` entry: if `key.lower() != "count"`, add a filter to the search segment via `add_filter(map_elastic_field(key), str(value), is_scalar(value), inclusive=True, condense=False)`. If `key == "count"` and `int(value) > async_threshold`, set `asynchronous = True`. The `count` pseudo-field ONLY toggles async; it is NOT added as a filter.
- Rebuild `parsed_query = Query() + search_segment` (baseline). `asynchronous = False` unless count threshold tripped.
- Call `update(criteria)`. If sync & no err & `updated_count == 0`: if `unchanged_count == 0` -> error `No eligible events available to acknowledge`, else `All events have already been acknowledged`.

Painless script builders (VERBATIM text asserted in tests; port exactly):
- `add_acknowledge_script(uc, now, esc, user_id)`: params `trackTiming = FEAT_RPT enabled`, `escBool = esc`, `nowMillis = now.unix_millis`, `userId`. Computes `elapsed_seconds` between `@timestamp` and now (ChronoUnit, ZoneId `Z` = UTC); if `event.acknowledged != true` sets `acknowledged=true`, `acknowledged_by=params.userId`, and (if track_timing) `acknowledged_timestamp`/`elapsed_seconds`; if `event.escalated != true && esc_bool` sets `escalated=esc`, `escalated_by=userId`, (if track_timing) timing fields. `userId` ALWAYS via params (injection-safe).
- `add_unacknowledge_script(uc)`: `ctx._source.event.acknowledged = false;` (no params).
- `add_investigate_script(uc, now, user_id, session_id?)`: sets `event.investigated=true`, `investigated_by=params.userId`; if session_id provided sets `investigation_session_id=params.sessionId`; timing gated on track_timing.
- `add_investigate_delete_script(uc)`: removes `investigation_session_id` if present.
- Public dispatchers to expose: `add_ack_escalate_update_scripts(uc, now, ack, esc, user_id)` and `add_investigation_update_scripts(uc, now, user_id, is_delete, session_id?)`.

#### 4.1.2 Field-caps cache

- `_refresh_cache`: under an `asyncio.Lock`, if cache_time is unset or older than `cache_ms`, call `es.field_caps(index=split(index), fields='*')`, parse the `fields` object into `dict[name -> FieldDefinition(name, field_type, aggregatable, searchable)]`, then set cache_time = now.
- **Multi-type rule (load-bearing):** when a field name has multiple type entries, PREFER the NON-aggregatable definition (keeps non-aggregatable unless none set yet). This drives `.keyword` remapping.
- `cache_ms` default 86400000 (24h). Reuse `fieldcaps_response.json` as a fixture.

#### 4.1.3 Tasks parsing (`convertFromElasticQueryTaskResults`)

- Parse into `{nodes: {id: {tasks: {task_id: ElasticTask}}}}`. Pydantic models with aliases: `cancellable`, `action`, `type`, `start_time_in_millis`, `running_time_in_nanos`, `parent_task_id`. A non-numeric (string) numeric field is an unmarshal error.
- If `filter`, exclude when `not cancellable` OR `type == "persistent"` OR `parent_task_id` non-empty OR `action == "cluster:monitor/tasks/lists"`.
- Build `QueryTask(task_id=..., cancelable=cancellable, details=f"{type} ({action})", start_time=Unix(start_time_in_millis), elapsed_ms=running_time_in_nanos // 1e6, grid_id=grid_id, es_client=client)`.

GOTCHA — Go latent bugs in `getActiveQueries`: (1) it calls `store.esClient.Tasks.List` inside the loop instead of the loop's `client`; (2) its error checks reference a pre-existing `err` var so first-iteration errors are effectively swallowed. The Python port should FIX both (use each client; check each iteration's error) — fixing is cleaner and the bug only matters in multi-cluster setups. `cancelQuery` correctly executes via the matched task's client even though it builds options from primary — preserve "cancel on the task's own client".

### 4.2 Casestore (`ElasticCasestore`)

Two indices: `index` (live, all kinds discriminated by `so_kind`) and `audit_index` (immutable history snapshot per create/update/delete). `schema_prefix` default `so_` prefixes every field/kind/audit key.

The audit/dual-write pattern (central): every mutating op writes the live doc, then an immutable audit snapshot into `audit_index` with `so_audit_doc_id = live _id` and `so_operation in {create, update, delete}`. Audit-write failure is logged, NON-fatal. Single-doc writes use `refresh=True`; bulk uses `refresh="wait_for"`.

| Go | Python port | ES API | Behavior / gotchas |
| --- | --- | --- | --- |
| `Create` | `create(case) -> Case` | search(template?) + index x2 + search(read-back) | Force `status="new"`. `validate_case`. Reject `id != ""` (`invalid ID for caseId`). applyTemplate if `template` set. `create_time=now`. `save(kind="case")`. Read-after-write via `get_case(document_id)`. |
| `Update` | `update(case) -> Case` | search + index x2 + search | `validate_case`. Require id (`Missing case ID`). Get old. Preserve `create_time/complete_time/start_time`. `process_workflow_for_status(old)` (closed -> complete_time=now; in progress -> start_time=now else keep). `save`. Read back. NO seq_no (last-write-wins). |
| `GetCase` | `get_case(id) -> Case \| None` | search size 1 | `validate_id`. Lucene `_index:"<index>" AND so_kind:"case" AND _id:"<id>"`. Service returns None when missing (no raise). |
| `GetCaseHistory` | `get_case_history(id) -> list[Any]` | search sorted `@timestamp^` | `validate_id`. AUDIT index, OR clauses on `audit_doc_id`/`comment.caseId`/`related.caseId`/`artifact.caseId`. Heterogeneous list by kind. |
| `CreateRelatedEvents` | `create_related_events(events) -> (int, dict[str,str], None\|str)` | search + bulk x2 + search/index per observable | See §4.2.1. |
| `GetRelatedEvent` | `get_related_event(id) -> RelatedEvent \| None` | search size 1 | `validate_id`; `so_kind:"related"`. |
| `GetRelatedEvents` | `get_related_events(case_id) -> list[RelatedEvent]` | search (no sortby) + in-memory sort | `validate_id`. NO server-side sortby (ES 8.4 flattened-field bug). Then sort ascending by `fields["timestamp"]` when a datetime; records lacking a datetime sort FIRST. Replicate manual sort + missing-key behavior. |
| `DeleteRelatedEvent` | `delete_related_event(id) -> None` | search + delete + index(audit) | `validate_id`; get (404 if missing); delete(`related`). |
| `CreateComment` | `create_comment(comment) -> Comment` | search(GetCase) + index x2 + search | `validate_comment`; reject id; reject empty case_id; `get_case`; `create_time=now`; `save("comment")`; read back. `hours` only when FEAT_TTR. |
| `GetComment` | `get_comment(id) -> Comment \| None` | search size 1 | `validate_id`; `so_kind:"comment"`. (Not wrapped by CaseService but must exist.) |
| `GetComments` | `get_comments(case_id) -> list[Comment]` | search sorted `so_comment.createTime^` | `validate_id`. |
| `UpdateComment` | `update_comment(comment) -> Comment` | search + index x2 + search | `validate_comment`; require id; preserve old `create_time`; `save`; read back. |
| `DeleteComment` | `delete_comment(id) -> None` | search + delete + index(audit) | Relies on `get_comment -> validate_id` (no direct validate). delete(`comment`). |
| `CreateArtifact` | `create_artifact(artifact) -> Artifact` | search + index x2 + search | `validate_artifact`; reject id/empty case_id/empty group_type; `get_case`; `create_time=now`; `save("artifact")`; read back. |
| `GetArtifact` | `get_artifact(id) -> Artifact \| None` | search size 1 | `validate_id`. |
| `GetArtifacts` | `get_artifacts(case_id, group_type, group_id) -> list[Artifact]` | search sorted `so_artifact.createTime^` | `validate_id` on all set params. group_id optional. |
| `UpdateArtifact` | `update_artifact(artifact) -> Artifact` | search + index x2 + search | Require id. **Preserve from old:** create_time, artifact_type, value, group_type, group_id, stream_len, mime_type, stream_id, md5, sha1, sha256. Only description/tlp/tags/ioc/protected updatable. |
| `DeleteArtifact` | `delete_artifact(id) -> None` | search + (stream del) + (Datastore jobs) + delete + audit | If `stream_id`, `delete_artifact_stream` (fail-soft). If Datastore present, GetJobs(analyze, {artifact:{id}}) + DeleteJob each (fail-soft). delete(`artifact`). Datastore is a separate dependency — inject a cleanup hook or no-op. |
| `CreateArtifactStream` | `create_artifact_stream(stream) -> str` | index x2 (no read-back) | `validate_artifact_stream`; reject id; `create_time=now`; `save("artifactstream")`; return `document_id`. |
| `GetArtifactStream` | `get_artifact_stream(id) -> ArtifactStream \| None` | search size 1 | `validate_id`. |
| `DeleteArtifactStream` | `delete_artifact_stream(id) -> None` | search + delete + audit | get + delete(`artifactstream`). (Not wrapped by CaseService but must exist.) |
| `GetCaseIdsWithArtifact` | (not on the listed Protocol; used by assistant) | search + dedup | `validate_string_required` on artType/value; EscapeLucene them; collect unique `caseId` first-seen order. |
| `ExtractCommonObservables` | helper | search + index per observable | Iterates ALL `event.fields`; new+in common_observables+non-empty -> create_artifact (RETURNS error, unlike inline). |

Validation helpers (error strings VERBATIM):
- `validate_id(id, label)`: regex `^[A-Za-z0-9-_]{5,50}$` else `invalid ID for <label>`.
- `validate_string(str, max, label)` / `validate_string_required(str, min, max, label)`: too long -> `<label> is too long (len/max)`; too short -> `<label> is too short (len/min)`. Use UTF-8 byte length (`len(s.encode("utf-8"))`) to match Go `len()`.
- `validate_string_array(arr, max_len, max_elements, label)`: excess -> `Field '<label>' contains excessive elements (len/maxElements)`; element label is literally `Tag[<idx>]`.
- `validate_case`: first-error-wins. Severity is run through `convert_severity` and MUTATES (`'2'` -> `medium`, `''` -> `high`). Kind/Operation must be empty. Check ORDER is load-bearing.
- `validate_related_event`: `len(fields) == 0` -> `Related event fields cannot not be empty` (double-negative typo VERBATIM).
- `validate_artifact`: `stream_len != 0 AND artifact_type != "file"` -> `Invalid streamLength`; group_type validated as ID (REQUIRED); value checked before group_type.
- `validate_artifact_stream`: `len(content) == 0` -> `Missing stream content`.

`prepare_for_save(obj)`: set `user_id` from requestor context; capture+clear `id` (return it for ES `_id`); null `update_time`. Empty returned id => ES auto-generates.

`save(obj, kind, id)`: AuthZ(write,cases). doc = `{prefix+kind: obj, "@timestamp": now, prefix+"kind": kind}`. Index into live index with id. On success mutate doc: `prefix+"audit_doc_id"=document_id`, `prefix+"operation"="create" if id=="" else "update"`, index into audit index with empty id.

`delete(obj, kind, id)`: AuthZ(write,cases). Delete from live index by id. On success build audit doc with `operation="delete"`, index into audit index. Does NOT remove history.

`get(id, kind)`: Lucene `_index:"<index>" AND <prefix>kind:"<kind>" AND _id:"<EscapeLucene(id)>"`; `get_all(query, 1)`; first or error `Object not found`. The kind constant is also EscapeLucene'd.

`get_all(query, max)`: AuthZ(read,cases). `EventSearchCriteria.populate(query, "<zero> - <now>", "%Y-%m-%d %I:%M:%S %p", now.tz, metric_limit="0", event_limit=str(max))`. Eventstore search. Conversion errors per-record are logged + skipped (non-fatal).

`BuildBulkIndexer`: `refresh="wait_for"`. Python: `elasticsearch.helpers.async_bulk(refresh="wait_for")` or batched `_bulk`.

`ConvertObjectToDocument(kind, obj, auditable, is_edit, audit_doc_id, op)`: index = live if `audit_doc_id is None` else audit; strip leading `*:`; doc via `convert_object_to_document_map` + `prefix+"kind"=kind`; if audit_doc_id set add `prefix+"audit_doc_id"` and (if op) `prefix+"operation"`; if `is_edit` wrap as `{"doc": document}`. Returns `(body_dict, index)`.

`Observables.GetType(expr)` (`observables.go`): ordered matchers, return first match. Order: ip, domain, fqdn, url, filename, uriPath, hash; default `other`. IP via `ipaddress.ip_address` try/except (IPv4+IPv6); others regex. Regexes: URL=`^[a-zA-Z]+://`; FQDN=`^(([a-z0-9][a-z0-9\-]*[a-z0-9]|[a-z0-9])+\.){2,}([a-z]{2,}|xn\-\-[a-z0-9]+)\.?$`; Domain=`^([a-z0-9][a-z0-9\-]*[a-z0-9]|[a-z0-9])\.([a-z]{2,}|xn\-\-[a-z0-9]+)\.?$`; Filename=`(\/)?[\w,\s-]+\.[A-Za-z]{3}$`; URIPath=`^\/[\w,\s-]`; Hash=`^[0-9a-fA-F]{32}$|{40}$|{64}$|{128}$`. Order matters (domain before fqdn, ip first).

#### 4.2.1 CreateRelatedEvents

Per event: `validate_related_event`; reject `id != ""` / empty `case_id`; errMap keyed by `fields["soc_id"]`. Group by case_id, cap per case at `max_bulk_escalate_events` (alerting params). Per case: skip empty; `get_case` (else all error); `get_related_events` -> set of existing `soc_id`; duplicate -> `ERROR_CASE_EVENT_ALREADY_ATTACHED`. Bulk #1 `create` related docs into live index; on success increment + collect `AuditInfo`. Bulk #2 `create` audit docs into audit index (failures prefixed `AUDIT: `). Then auto-extract observables INLINE: `get_artifacts(case_id, "evidence", "")` existing-value set; per event per `common_observables` field present & non-empty & new -> `create_artifact` (errors warn-logged only, swallowed). Returns `(total_created, err_map, fatal_err)`. Use `action="create"` (fails on existing _id). Python async: use `async_bulk` or serial awaited loop with a single accumulator (no mutex needed).

Note: observable extraction logic is DUPLICATED with differences — inline here (iterates common_observables, swallows errors) vs `extract_common_observables` (iterates fields, returns error). Port both faithfully or consolidate carefully.

### 4.3 Detectionstore (`ElasticDetectionstore`)

Same audit/dual-write pattern. Detection identity: `detection._id` (onion id) = `util.ToUUID(public_id)`; uniqueness key = `(public_id, engine)`.

| Go | Python port | ES API | Behavior / gotchas |
| --- | --- | --- | --- |
| `CreateDetection` | `create_detection(d) -> Detection` | search(dup) + index x2 + search | `validate_detection`. Reject id (`Unexpected ID found in new comment` — VERBATIM, says comment). Dup check by `(public_id, engine)`; any hit -> error containing `already exists` (`publicId already exists for this engine`). `create_time=now`; `d.id = to_uuid(public_id)`; override-operation `create` (keeps id in body); `save`; read back. |
| `GetDetection` | `get_detection(id) -> Detection` | search size 1 | `validate_id`. NON-optional — expected to RAISE on miss (service accesses `.engine`). `get(id, "detection")`. |
| `GetDetectionByPublicId` | `get_detection_by_public_id(pid) -> Detection \| None` | search size 1 | `validate_public_id`. Returns `(None)` when not found. |
| `UpdateDetection` | `update_detection(d) -> Detection` | index x2 + search | `validate_detection`. Require id (`Missing detection onion ID`). `prepare_for_save` mutates id; defer-restore. operation defaults `update`. Honors skip_audit. Re-read. |
| `DeleteDetection` | `delete_detection(id) -> Detection` | search + delete + index(audit) | AuthZ(write,detections). `get_detection(id)` (`not found` if missing). `delete_document(...)`. Returns the pre-delete object (service flips `is_enabled=False` and resyncs). |
| `GetDetectionHistory` | `get_detection_history(id) -> list[Any]` | search sorted `@timestamp^` | AUDIT index, OR `audit_doc_id`/`detectioncomment.detectionId`. **NO validate_id** — relies on EscapeLucene only. Heterogeneous list. |
| `CreateComment` | `create_comment(c) -> DetectionComment` | search(parent) + index x2 + search | `validate_comment`. Reject id; reject empty detection_id (`Missing Detection ID in new comment`); `get_detection` (parent must exist). `create_time=now`; `save`; read back. |
| `GetComment` | `get_comment(id) -> DetectionComment` | search size 1 | `validate_id`. |
| `GetComments` | `get_comments(detection_id) -> list[DetectionComment]` | search sorted `detectioncomment.createTime^` | `validate_id`. |
| `UpdateComment` | `update_comment(c) -> DetectionComment` | search + index x2 + search | Require id; preserve old `create_time`. |
| `DeleteComment` | `delete_comment(id) -> None` | search + delete + audit | `get_comment` then `delete_document`. |
| `DoesTemplateExist` | (not on listed Protocol) | `es.indices.get_index_template(name=tmpl)` | 200-299 -> True; 404 -> False (catch `NotFoundError`); transport errors propagate. |
| `BulkUpdateDetections` | (not on listed Protocol) | bulk x2 | Two-phase, see §4.3.1. |
| `BulkAddOverrides` | (not on listed Protocol) | bulk x2 | Same two-phase; uniform-language + engine-supported pre-checks; uses `detection.validate()`. |
| `GetAllDetections` | (not on listed Protocol) | scroll (limit -1) | Base query + GetAllOptions; `query(..., -1)` -> scroll; map keyed by public_id only. |
| `ConvertEventsToDetections` | helper | none | map + cast; skip conversion errors. |
| `QueryWithRange` | (not on listed Protocol) | search | `parse_range_allow_relative`; zone UTC; format `%Y/%m/%d %I:%M:%S %p`; sort `@timestamp desc`; raw EventSearchResults. |

`Query(max)`: AuthZ(read,detections). `max == -1` -> unlimited: cap 10000, uses Scroll over `[index]`. Else bounded search. GOTCHA: `-1` switches to scroll, not "return everything in one search".

Validation:
- `validate_id`: `^[A-Za-z0-9-_]{5,50}$`.
- `validate_public_id`: `^[A-Za-z0-9-_]{3,128}$` (looser; Suricata SIDs / Sigma UUIDs).
- `validate_detection`: sequential short-circuit on optional string fields, then ALWAYS validate engine in `ENGINES_BY_NAME` (`invalid engine`), language in supported (`invalid language`), `engine.sig_language == language` (`engine and language mismatch`), then Kind/Operation must be empty.
- `validate_comment`: Value required min 1.

`util.ToUUID(s)` (port BYTE-IDENTICAL — drives stable doc ids/dedupe/history linkage): SHA-256 -> XOR-fold 32->16 bytes -> fold 16->15 -> hex -> format `xxxxxxxx-xxxx-4xxx-bxxx-xxxxxxxxxxxx` with version nibble forced `4` and variant char forced `b`.

`util.EscapeLucene(v)` (port BYTE-IDENTICAL — sole injection guard where no validate_id): replace `\` with `\\` FIRST, THEN `"` with `\"` (order matters).

GOTCHA — hardcoded bulk indices: `BulkUpdateDetections`/`BulkAddOverrides` HARDCODE `so-detection`/`so-detectionhistory` inside `ConvertObjectToDocument`, ignoring `store.index`/`audit_index`. Non-bulk methods use the configured indices. Replicate this discrepancy (or writes go to the wrong place).

Context flags: replace Go's `modcontext` (skip_audit, override_operation) with explicit kwargs: `*, requestor_id, skip_audit=False, override_operation=None`.

#### 4.3.1 BulkUpdateDetections

Phase 1 (updates, `refresh="wait_for"`): per detect, look up engine in `DetectionEngines` (skip + errMap `unsupported engine` if missing); `is_enabled = new_status`; `engine.apply_filters` (FATAL err aborts whole op); count `filtered` if filter forced status back; `engine.extract_details` (skip + errMap on err); `ConvertObjectToDocument(is_edit=True, audit_doc_id=None)` -> `{"doc": {...}}` update action into `so-detection`. OnSuccess: updated++ + `AuditInfo{doc_id, op:"update", object}`. OnFailure: errMap[public_id]. Phase 2 (audit): per AuditInfo, `ConvertObjectToDocument(is_edit=False, audit_doc_id=&doc_id, op=&op)` -> create into `so-detectionhistory`; audited++; mark `persist_change=True`, collect dirty. Return `BulkUpdateStats{updated, audited, filtered, err_map(keyed by public_id), update_duration, need_to_sync=dirty}`. Go uses mutexes; Python async use a single accumulator.

### 4.4 Assistantstore (`ElasticAssistantstore`)

Two indices: `chat_index`, `session_index`. `schema_prefix` prefixes every field path and doc key. Soft delete via `delete_time`.

| Go | Python port | ES API | Behavior / gotchas |
| --- | --- | --- | --- |
| `SaveChat` | `save_chat(message) -> None` | `es.index(refresh=True)` | AuthZ(write_authored,assistant); `validate_chat`; `create_time=now`; `prepare_for_save`; `save(chat_index, "chat")`. Doc body uses StoredMessage STORAGE shape (see gotcha). ES auto-generates _id. |
| `GetChatHistory` | `get_chat_history(session_id) -> list[StoredMessage]` | search + nested get_sessions + msearch | `get_sessions(session_id=..., include_deleted=True)`; if zero -> error `Object not found`. Per-session ownership authz: owner -> read_authored; `shared` tag -> read_shared; else read_all. Build bool (term `chat.sessionId`, term `kind=="chat"`), sort `@timestamp asc`, size 10000. Parse `_source[prefix+"chat"]` -> StoredMessage (storage shape); `kind` from `_source[prefix+"kind"]`; id from `_id`. **Service treats a `not found` error as empty history — prefer returning `[]` for unknown sessions** (raising tolerated only if message contains `not found`). Test asserts exactly 3 ES requests (get_sessions, addMetaFromMessages msearch, chat-history search). |
| `GetSessions` | `get_sessions(query: GetSessionsQuery) -> list[AssistantSession]` | search + msearch (always meta) + optional msearch (usage) | See §4.4.1. |
| `CreateSession` | `create_session(session) -> None` | `es.index(refresh=True)` | AuthZ(write_authored,assistant); `validate_session` (valid session_id + non-empty title, else `Title is too short`); `create_time=now`; `prepare_for_save`; `save(session_index, "session")`. |
| `UpdateSessionTags` | `update_session_tags(session_id, tags) -> None` | `es.update_by_query(refresh=True, wait_for_completion=True)` | AuthZ(write_authored,assistant). Owner-scoped query (term session_id, term `session.userId == requestor`). Painless `ctx._source.<prefix>session.tags = params.tags;` params `{tags}`. Replaces tags wholesale. Cross-cluster prefix stripped. Non-owner matches 0 docs and silently succeeds. |
| `DeleteSession` | `delete_session(session_id) -> None` | `es.update_by_query(refresh=True, wait_for_completion=True)` | AuthZ(delete_authored,assistant). SOFT DELETE: painless `ctx._source.<prefix>session.deleteTime = params.deleteTime;` params `{deleteTime: now RFC3339}`. Owner-scoped. No hard delete anywhere. |
| `GetUsage` | `get_usage(start, end) -> list[UserUsage]` | search (size 0 agg) | AuthZ(read_all,assistant). See §4.4.2. |

Validation:
- `validate_id`: `^[A-Za-z0-9-_]{5,50}$` (`re.fullmatch(r"[A-Za-z0-9_-]{5,50}", id)`).
- `validate_chat`: `validate_id(session_id)`. Exactly-one-of content: count ContentBlocks (non-empty -> +1; a block with empty `type` AND no `tool_result` -> error `every content block must have a type`; empty-text text blocks are filtered, not rejected) and ContentStr (non-empty -> +1). `count != 1` -> `message must have exactly one content type: either ContentBlocks or ContentStr`.
- `validate_session`: `validate_id(session_id)`; title non-empty.

`prepare_for_save`: set user_id from requestor; clear id (unless override-operation); null update_time. On read, id comes from ES `_id`.

`save(obj, index, kind)`: doc = `{prefix+kind: obj, "@timestamp": now, prefix+"kind": kind}`; `es.index(disableCrossClusterIndex(index), body, refresh=True)`.

#### 4.4.1 GetSessions

`GetSessionsQuery` (pydantic, no aliases): `user_id`, `session_id`, `include_deleted`, `with_usage`, `start`, `end`. Build bool: must always `term prefix+"kind" == "session"`; if user_id -> `term prefix+"session.userId"`; if session_id -> `term prefix+"session.sessionId"`; if NOT include_deleted -> `must_not exists prefix+"session.deleteTime"`; if start AND end both set -> `range @timestamp {gte, lte}` (RFC3339). Sort `@timestamp asc`, size 10000. Parse `_source[prefix+"session"]` -> AssistantSession; skip hits with no session sub-object (partial-malformed tolerated). Then:
1. `filter_shared_sessions` (per-session authz, MEMOIZED): owner -> read_authored; `shared` tag -> read_shared; else read_all (resource `assistant`). Cache the three `Optional[bool]` results. Dropped sessions are filtered out.
2. If `with_usage` -> `populate_session_usage` (error aborts).
3. ALWAYS -> `add_meta_from_messages` (error aborts; bad date string aborts whole GetSessions).

NO top-level CheckAuthorized — authz is entirely per-session in the filter.

`populate_session_usage` (msearch over chat_index, header `{}` to inherit request index): per session a body with bool must (term chat.sessionId, term kind=="chat"), size 0, aggs `total_input_tokens`/`total_output_tokens`/`total_credits` (sum on `chat.message.usage.{input_tokens,output_tokens,credits}`), `total_messages` (value_count `chat.sessionId`), `model_usage` (terms `chat.model` size 100 with sub sums + value_count). Responses aligned POSITIONALLY to sessions[i]; per-response `error` key -> warn + skip (Usage left None). Float -> int truncation. Bucket key `""` skipped.

`add_meta_from_messages` (msearch, always): per session aggs `update_time = max(prefix+"chat.createTime")` format `strict_date_optional_time`. Read `value_as_string` (NOT numeric value), parse RFC3339; on parse error RETURN error (aborts). Sets `session.update_time`.

#### 4.4.2 GetUsage

Single search, size 0: query bool must (term kind=="chat", range `@timestamp {gte,lte}`); aggs `users` = terms(`chat.userId`, size 10000) with sub-aggs total_input/output/credits (sum), total_messages (value_count `chat.userId`), total_sessions (cardinality `chat.sessionId`), model_usage (terms `chat.model` size 100). Range is on `@timestamp` (index-time), NOT `chat.createTime`. All numeric agg values are JSON floats -> cast to int.

GOTCHA — StoredMessage has TWO JSON shapes: `Message` LLM-facing (`content`, `stop_reason`, `stop_sequence`) vs the STORAGE `saveableMessage` shape (`contentStr`, `contentBlocks`, `stopReason`, `stopSequence`, `thoughts`, `usage`). The ES document under `so_chat.message` uses the STORAGE shape. The Python port persists/reads with storage-shaped keys. `Message.model_dump` is overridden (by_alias + exclude_none; content_str-vs-content_blocks switch; selectively emits id/thoughts/stop_reason/stop_sequence/usage) — route persistence through it.

### 4.5 Index/document shapes summary

Write envelope (all stores): `{"@timestamp": <now>, "<prefix><kind>": <object body>, "<prefix>kind": <kind>}`; audits add `"<prefix>audit_doc_id"` + `"<prefix>operation"`.

Read shape: `_source` returns FLATTENED dotted keys (`so_case.title`, `so_detection.publicId`), EXCEPT `overrides` (nested). `Auditable.id` from `_id`, not body.

### 4.6 Job-lookup handler (PopulateJobFromDocQuery) — separate concern

This hangs off `ElasticEventstore` (queries EVENTS indices, not detection) and the generic Job/Datastore pipeline. Port as a SEPARATE FastAPI route once event-search + Job/Datastore services exist (not part of any storage Protocol).

HTTP `GET /connect/joblookup/`: params `time`, `esid` (ES `_id`) else `ncid` -> field `network.community_id`. Create job. `populate_job_from_doc_query(id_field, id_value, timestamp_str, job)`. 404 if no doc. AddPivotJob; broadcast `job`; redirect 302 to `#/job/<id>`.

`populate_job_from_doc_query` behavior:
- `validate_id(id_value)` with regex `^[A-Za-z0-9\-_]{3,128}$` BEFORE any query (injection test asserts 0 requests for malicious id).
- Range filter `+/- es_search_offset_ms` (epoch_millis, `Unix() * 1000`, truncates sub-second) around timestamp if given.
- Primary lucene search bool.must `[{match: {id_field: id_value}}]` + range. 0 hits -> error `Unable to locate document record`.
- Derive timestamp from `hits.0._source.@timestamp` if not given.
- If `lookup_tunnel_parent` and record has `log.id.tunnel_parents`, re-search by `log.id.uid = tunnel_parents[0]`.
- Extract: `import.id`, `network.transport` (lowercased) -> Protocol, source.ip/port, destination.ip/port, `log.id.uid` (parseFirst [0] if array), `log.id.id` (x509), `log.id.fuid`, `suricata.capture_file` param, `observer.name` -> sensor_id. duration = default_duration_ms.
- If IP/port incomplete and protocol != icmp: if uid empty or not starting `C`, Zeek file search (`event.dataset:zeek.file AND <EscapeLucene(fuid/x509id)>`), then Zeek conn search (`event.module:zeek AND <EscapeLucene(uid)>`); among conn hits pick record with `@timestamp` nearest original timestamp that has full IP/port (or icmp), update filter + duration (`event.duration * 1000` rounded).
- Final validation: require src/dst ip and (ports or icmp) else error.
- Set filter `begin_time = ts - (duration + time_shift_ms)`, `end_time = ts + (duration + time_shift_ms)`. `job.set_node_id(sensor_id)`; `job.filter = filter`.
- All queries built as dicts -> json (no string interpolation). Keep validation-first + Lucene escaping.

---

## 5. Python implementation strategy

### 5.1 Module layout

```
backend/src/adapters/elastic/
  __init__.py
  config.py            # Pydantic settings (snake_case) + defaults from §2.1
  client.py            # AsyncElasticsearch construction, run-as header, client list
  converter.py         # PURE builders + parsers (§3) — no ES client, fully unit-testable
  fields.py            # FieldDefinition + map/unmap_elastic_field + field-caps cache
  scripts.py           # painless ack/investigate builders (VERBATIM)
  util.py              # validate_id/validate_public_id, escape_lucene, to_uuid, transform_index, disable_cross_cluster_index, truncate, validate_string*
  observables.py       # observable classifier
  eventstore.py        # ElasticEventstore(Eventstore)
  casestore.py         # ElasticCasestore(Casestore)
  detectionstore.py    # ElasticDetectionstore(Detectionstore)
  assistantstore.py    # ElasticAssistantstore(Assistantstore)
  joblookup.py         # PopulateJobFromDocQuery + FastAPI route (later)
```

### 5.2 Pure vs I/O split

- Converter builders return dicts; parsers take dicts/JSON and return domain objects. They never touch the network. Unit-test with JSON fixtures (`converter_response.json`, `converter_response_failure.json`, `fieldcaps_response.json`) + assert JSON via `json.dumps(sort_keys=True)`.
- Each store's public method is thin: AuthZ -> refresh_cache (if needed) -> build -> `await self._client...` -> parse. Mock the `AsyncElasticsearch` in unit tests (assert called URL/body/index counts — the Go tests assert exact request counts, e.g. casestore save = 2 Index calls, GetChatHistory = 3 ES requests).

### 5.3 Domain model mapping rules

- Event/query types (`event.py`, `query.py`) are PLAIN classes (no pydantic, no aliases) — map to/from ES JSON manually; populate attributes directly and call `results.complete()`.
- Case/detection/assistant types are pydantic v2 with `populate_by_name=True` + camelCase aliases — build via `model_validate(...)` (accepts alias or field name) and serialize via `model_dump(by_alias=True, exclude_none=...)`. Alias gotchas to NOT get wrong: `Artifact.stream_len -> "streamLength"`; `AiFields.is_ai_summary_stale -> "isSummaryStale"`; `OverrideType.CUSTOM_FILTER == "customFilter"`; assistant uses MIXED snake/camel aliases (`Usage.input_tokens/output_tokens`, `Message.stop_reason/stop_sequence`); `ToolResponse` has NO aliases.
- `EventResults.complete_time` defaults to `datetime.min` (UTC) sentinel = "not completed" — serializer should treat min-time as null/empty.
- StrEnums in `detection.py` serialize as values; `Detection.severity` default `Severity.UNKNOWN`.
- Float -> int via `int(float)` (truncate) for elapsed_ms/total_events/updated/unchanged/priority/stream_len/count/seconds.

### 5.4 Error-string contracts the services depend on

- `create_detection` MUST raise with message containing `already exists` on public-id collision (service maps to `PublicIdConflict`).
- `get_chat_history` may raise ONLY with `not found` in the message for unknown sessions (otherwise return `[]`).
- `get_detection` is non-optional and expected to raise on miss; `get_detection_by_public_id` returns Optional.
- `create_related_events` -> `(count, id_map, err)`; `create_artifact_stream` -> str id; `delete_detection` returns the deleted object.
- Keep all VERBATIM validation strings (`invalid ID for <label>`, `<label> is too long/short (x/y)`, `Object not found`, `Missing case ID`, `Unexpected ID found in new ...`, `ERROR_CASE_EVENT_ALREADY_ATTACHED`, `Related event fields cannot not be empty`, `engine and language mismatch`, `Field 'Kind' must not be specified`).

### 5.5 Testing

- Unit (no live ES): converter builders/parsers via fixtures + sort_keys equality; validators; `to_uuid`/`escape_lucene` byte-parity vectors; store methods with a mocked `AsyncElasticsearch` asserting request shapes/counts/indices/ids (mirror the Go test assertions).
- Integration: `docker-compose` Elasticsearch (single node, security off or test creds). Run the real adapter against it: index/search/scroll round-trip, update_by_query conflicts=proceed + refresh, audit dual-write, soft-delete filtering, field-caps cache, tasks list/cancel. Mark with a pytest marker so unit runs stay fast.

### 5.6 Wiring into `create_app`

`backend/src/main.py` builds the app with router includes and dependency overrides (currently uses stub/file adapters). To wire the ES adapter:
- Construct config from settings; build the client list; construct the four stores sharing the client(s).
- Provide them via FastAPI dependencies, replacing the stubs:
  - Eventstore -> `EventsService` (events_routes, query_routes), plus handler/job layers for `get_active_queries`/`cancel_query`.
  - Casestore -> `CaseService` (case_routes).
  - Detectionstore -> `DetectionService` (detection_routes).
  - Assistantstore -> `AssistantService` (assistant_routes).
- Field-caps cache: lazy-init on first search; share the asyncio lock per store instance.
- Joblookup route registered separately (packet/connect routes) once Job/Datastore services exist.

---

## 6. Risks, gotchas, and build order

### 6.1 Consolidated gotcha checklist

1. TLS: `verify_certs = verify_cert` (do NOT invert in Python despite Go's `InsecureSkipVerify = !verifyCert`).
2. Run-as header `es-security-runas-user` injected per-request when basic auth configured.
3. Update/Acknowledge FAN OUT over all clients; partial success tolerated (error reset to None if >=1 host succeeds); cross-cluster prefix stripped per client. Reads/index/delete/fieldcaps/tasks use primary only.
4. `update_by_query`: `conflicts="proceed"`, `refresh=True`; `noops` -> `unchanged_count`. Index uses `refresh=True`; Delete has no refresh; bulk uses `refresh="wait_for"`.
5. `disable_cross_cluster_index` on WRITES only; `{today}` transform on index/delete only.
6. Scroll keep-alive hardcoded 60s; size = max_scroll_size; ClearScroll 404 ignored; loop stops when page empty or collected >= total.
7. Scroll performs NO auth check; everything else does AuthZ with specific (op,target): read/events, write/events, ack/events, read/queries, delete/queries, read/write/delete cases/detections, write_authored/read_authored/read_shared/read_all/delete_authored assistant.
8. `get_active_queries` Go bug — FIX in Python (use each client; per-iteration error checks). `cancel_query` runs on the task's own client.
9. ID injection defense everywhere: `validate_id`/`validate_public_id` BEFORE any ES call; Lucene values escaped via `escape_lucene`; painless user_id/session_id only as params; msearch index header JSON-encoded.
10. field_caps multi-type: prefer NON-aggregatable entry.
11. Painless ack/investigate text asserted VERBATIM (ZoneId `Z`, ChronoUnit elapsed_seconds, FEAT_RPT-gated timing). Acknowledge `count` pseudo-field only toggles async.
12. Converter: `filter/should/must_not` always empty arrays; key ordering via `sort_keys=True`; space after colon in search serialization; `make_aggregation` strips `*` before `map_elastic_field`; sortby segment wins over sort_fields with a different JSON shape; msearch passes zero times (no range); `calc_timeline_interval` inclusive `<=` ladder.
13. `hits.total` number-or-object; timestamp fallback `@timestamp -> timestamp -> zero`; shard failures non-fatal but set `ERROR_QUERY_FAILED_ELASTICSEARCH`.
14. NEST-on-write / FLATTEN-on-read asymmetry for cases/detections (overrides stay nested).
15. Detection bulk methods HARDCODE `so-detection`/`so-detectionhistory`. `to_uuid`/`escape_lucene` BYTE-IDENTICAL.
16. No optimistic concurrency anywhere (no seq_no/if_seq_no) — read-modify-write last-write-wins.
17. Audit dual-write per mutation; audit failure non-fatal. Create/Update read back after save; CreateArtifactStream and bulk do NOT read back.
18. Assistant soft-delete via update_by_query; StoredMessage storage shape vs LLM shape; msearch responses aligned POSITIONALLY; `add_meta_from_messages` always runs and a bad date aborts GetSessions; range only when both start AND end set.
19. String lengths use UTF-8 BYTE length (`len(s.encode("utf-8"))`) to match Go `len()`.
20. GetRelatedEvents sorts in memory (ES 8.4 bug); missing-timestamp records sort first.

### 6.2 Recommended build order

1. Client + transport + config (§2) — get a live `AsyncElasticsearch`, run-as header, client list, TLS/timeout. Smoke-test connectivity against docker-compose.
2. Converter (§3) — pure builders + parsers + `map/unmap_elastic_field` + field-caps cache + `calc_timeline_interval`. Unit-test exhaustively with fixtures FIRST (TDD). This de-risks everything else.
3. Eventstore (§4.1) — search/scroll/update/index/delete/acknowledge/tasks + painless scripts. Depends on converter + cache.
4. Casestore (§4.2) — audit dual-write, validators, observables, bulk related events. Depends on Eventstore search/index/delete + bulk helper.
5. Detectionstore (§4.3) — CRUD + comments + `to_uuid` + template check + bulk (hardcoded indices). Depends on Eventstore + converter.
6. Assistantstore (§4.4) — chat/sessions/usage, soft-delete, msearch aggregations, StoredMessage storage shape.
7. Integration tests against docker-compose ES for all four stores.
8. Wiring into `create_app` (§5.6); joblookup route last.

Rationale: each layer depends on the one above; the pure converter is the highest-leverage, lowest-risk first target and unblocks all stores.
