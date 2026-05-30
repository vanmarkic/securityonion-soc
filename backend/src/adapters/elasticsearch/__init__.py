"""Elasticsearch storage adapter — implements the Eventstore, Casestore,
Detectionstore, and Assistantstore ports against Elasticsearch.

Documented divergences from the Go reference (server/modules/elastic/), also
noted in the relevant module docstrings:

- No ``CheckAuthorized`` inside the stores — authorization is enforced at the
  route/service layer in this hexagonal architecture, not in the adapter.
- No ``es-security-runas-user`` header is sent; the rewrite does not impersonate
  the requesting user against Elasticsearch.
- ``ElasticEventstore.get_active_queries`` uses the loop's own client rather than
  the primary client — fixing a bug present in the Go implementation.
- Assistant per-session authorization filtering is dropped (the AI manager is a
  behavioral port out of scope for the storage adapter).

The stores share one ``ElasticClients`` (primary + remotes) so the connection
pool is not fanned out per route; they are wired into ``create_app`` only when an
``elastic``/``elasticsearch`` config block with a host is present (the default
app stays unwired and override-free).
"""
