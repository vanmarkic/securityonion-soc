"""Field-capabilities cache and field map/unmap helpers.

Pure port of the field-definition handling in
``server/modules/elastic/elasticeventstore.go`` (``FieldDefinition``,
``mapElasticField``, ``unmapElasticField``, ``cacheFields``) plus the lazy/TTL
cache wrapped around the Go ``refreshCache``/``cacheFieldsFromJson`` pair.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class FieldDefinition:
    name: str
    field_type: str
    aggregatable: bool
    searchable: bool


def parse_field_caps(data: dict[str, Any]) -> dict[str, FieldDefinition]:
    """Parse a raw ``_field_caps`` response into ``{name: FieldDefinition}``.

    Mirrors Go ``cacheFields``: when a field reports multiple type entries the
    NON-aggregatable definition is preferred (we cannot reliably aggregate
    across all indices; the ``.keyword`` subfield is used for aggregation).
    """
    out: dict[str, FieldDefinition] = {}
    for name, types in data.get("fields", {}).items():
        for _typ, meta in types.items():
            fd = FieldDefinition(
                name,
                meta.get("type", ""),
                bool(meta.get("aggregatable")),
                bool(meta.get("searchable")),
            )
            existing = out.get(name)
            # Go: store when nothing yet OR when the new def is non-aggregatable
            # (so any non-aggregatable type wins over an aggregatable one).
            if existing is None or (existing.aggregatable and not fd.aggregatable):
                out[name] = fd
    return out


def map_elastic_field(defs: dict[str, FieldDefinition], field: str) -> str:
    """Remap a non-aggregatable field onto its aggregatable ``.keyword`` twin."""
    fd = defs.get(field)
    if fd is not None and not fd.aggregatable:
        kw = defs.get(field + ".keyword")
        if kw is not None and kw.aggregatable:
            return field + ".keyword"
    return field


def unmap_elastic_field(defs: dict[str, FieldDefinition], field: str) -> str:
    """Strip ``.keyword`` when the base field is non-aggregatable."""
    suffix = ".keyword"
    if field.endswith(suffix):
        base = field[: -len(suffix)]
        fd = defs.get(base)
        if fd is not None and not fd.aggregatable:
            return base
    return field


class FieldCapsCache:
    """Lazy/TTL field-caps cache (asyncio.Lock + cache_ms TTL)."""

    def __init__(self, cache_ms: int) -> None:
        self._cache_ms = cache_ms
        self._defs: dict[str, FieldDefinition] = {}
        self._cache_time = 0.0
        self._lock = asyncio.Lock()

    @property
    def defs(self) -> dict[str, FieldDefinition]:
        return self._defs

    async def refresh(
        self, fetch: Callable[[], Awaitable[dict[str, Any]]]
    ) -> None:
        """Refresh the cache if the TTL has elapsed.

        ``fetch`` is an async callable returning the raw ``_field_caps`` JSON.
        """
        async with self._lock:
            now = time.monotonic() * 1000.0
            if self._cache_time != 0.0 and (now - self._cache_time) < self._cache_ms:
                return
            self._defs = parse_field_caps(await fetch())
            self._cache_time = now
