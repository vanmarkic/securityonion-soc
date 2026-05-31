"""Stub InfoProvider — in-memory adapter for development."""

from __future__ import annotations

from typing import Any
from zoneinfo import available_timezones

from src.domain.info import LicenseKey


class StubInfoProvider:
    """Returns hardcoded dev values. Satisfies the InfoProvider protocol."""

    async def get_version(self) -> str:
        return "dev-stub"

    async def get_elastic_version(self) -> str:
        return "8.13.0"

    async def get_license_info(self) -> tuple[str, str, LicenseKey]:
        lk = LicenseKey(
            effective="0001-01-01T00:00:00Z",
            expiration="0001-01-01T00:00:00Z",
            name="",
            id="",
            licensee="",
            features=["api", "fps", "gmd", "lks", "ntf", "odc", "qry", "stg", "ttr", "rpt", "vrt", "oai"],
            users=0,
            nodes=0,
            soc_url="",
            data_url="",
        )
        return "Elastic License 2.0 (ELv2)", "invalid", lk

    async def get_timezones(self) -> list[str]:
        return sorted(available_timezones())

    async def get_mgmt_mac(self) -> str:
        return "00:00:00:00:00:00"

    async def get_parameters(self) -> dict[str, Any]:
        """Client UI parameters (Go model.ClientParameters).

        The Vue frontend reads these on every page (the help nav binds
        docsUrl/cheatsheetUrl/releaseNotesUrl), so a non-null object is
        required — a null here makes the app throw ``Cannot read properties of
        null (reading 'docsUrl')``. The nested per-feature blocks are empty
        objects (their page components read into them lazily). Real values come
        from server config in a production InfoProvider; these are dev defaults.
        """
        return {
            "hunt": {},
            "alerts": {},
            "cases": {},
            "case": {},
            "dashboards": {},
            "job": {},
            "detections": {},
            "detection": {},
            "grid": {},
            "assistant": {},
            "docsUrl": "https://docs.securityonion.net/",
            "cheatsheetUrl": "https://docs.securityonion.net/en/2.4/cheat-sheet.html",
            "releaseNotesUrl": "https://docs.securityonion.net/en/2.4/release-notes.html",
            "webSocketTimeoutMs": 0,
            "tipTimeoutMs": 30_000,
            "apiTimeoutMs": 30_000,
            "cacheExpirationMs": 0,
            "inactiveTools": [],
            "tools": [],
            "casesEnabled": True,
            "detectionsEnabled": True,
            "exportNodeId": "",
        }
