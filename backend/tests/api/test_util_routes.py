"""Tests for util routes — ported from Go server/utilhandler_test.go."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.util_routes import get_util_service
from src.services.util_service import UtilService


class FakeReverseLookupProvider:
    """Stub that returns canned results for IP lookups.

    Simulates the Go test behavior: ES lookup finds "4.0.0.4" -> "host4",
    and when DNS is enabled, the remaining valid IPs get DNS results.
    """

    def __init__(self, *, enable_dns: bool = False) -> None:
        self.enable_dns = enable_dns
        # Simulates ES returning a result for 4.0.0.4
        self.es_results: dict[str, list[str]] = {"4.0.0.4": ["host4"]}

    async def reverse_lookup(self, ips: list[str], enable_dns: bool) -> dict[str, list[str]]:
        results: dict[str, list[str]] = {}

        # Filter to valid IPs only (matching Go's net.ParseIP behavior)
        valid_ips: list[str] = []
        for ip in ips:
            parts = ip.split(".")
            if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
                valid_ips.append(ip)

        # Dedup
        seen: set[str] = set()
        deduped: list[str] = []
        for ip in valid_ips:
            if ip not in seen:
                seen.add(ip)
                deduped.append(ip)

        # ES lookup
        remaining: list[str] = []
        for ip in deduped:
            if ip in self.es_results:
                results[ip] = self.es_results[ip]
            else:
                remaining.append(ip)

        # DNS lookup if enabled
        if enable_dns:
            for ip in remaining:
                # Simulate DNS returning the IP itself as a fallback
                results[ip] = [ip]

        return results


def _make_app(provider: FakeReverseLookupProvider | None = None, enable_dns: bool = False):
    from fastapi import FastAPI
    from src.api.util_routes import router

    test_app = FastAPI()
    test_app.include_router(router, prefix="/api")

    if provider is not None:
        service = UtilService(reverse_lookup_provider=provider, enable_reverse_lookup=enable_dns)
        test_app.dependency_overrides[get_util_service] = lambda: service

    return test_app


class TestReverseLookup:
    """Ported from TestReverseLookupHandler."""

    async def test_no_dns(self):
        """Without DNS enabled, only ES results should be returned."""
        provider = FakeReverseLookupProvider(enable_dns=False)
        test_app = _make_app(provider, enable_dns=False)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.put(
                "/api/util/reverse-lookup",
                json=["1.0.0.1", "2.0.0.2", "3.0.0.3", "4.0.0.4", "badip"],
            )
        assert resp.status_code == 200
        results = resp.json()
        # Only 1 result: "4.0.0.4" from ES
        assert len(results) == 1
        for names in results.values():
            assert len(names) > 0
        assert results["4.0.0.4"] == ["host4"]

    async def test_with_dns(self):
        """With DNS enabled, ES results + DNS fallback results should appear."""
        provider = FakeReverseLookupProvider(enable_dns=True)
        test_app = _make_app(provider, enable_dns=True)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.put(
                "/api/util/reverse-lookup",
                json=["1.0.0.1", "2.0.0.2", "3.0.0.3", "4.0.0.4", "badip"],
            )
        assert resp.status_code == 200
        results = resp.json()
        # 4 results: 4.0.0.4 from ES + 3 remaining valid IPs from DNS
        assert len(results) == 4
        for names in results.values():
            assert len(names) > 0
        assert results["4.0.0.4"] == ["host4"]
