"""Kratos Userstore — maps Ory Kratos identities to User domain model.

Ported from Go server/modules/kratos/kratosuserstore.go and kratosuser.go.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.domain.user import User

logger = logging.getLogger(__name__)


def _map_identity_to_user(identity: dict[str, Any]) -> User:
    traits = identity.get("traits", {})
    state = identity.get("state", "active")
    credentials = identity.get("credentials", {})

    # Go copyToUser sets totp/webauthn to "disabled" when the credential is absent
    # but other credentials exist; we simplify to "" since the User model only needs
    # the enabled/empty distinction for the rewrite.
    totp_status = "enabled" if "totp" in credentials else ""
    webauthn_status = "enabled" if "webauthn" in credentials else ""

    return User(
        id=identity.get("id", ""),
        email=traits.get("email", ""),
        first_name=traits.get("firstName", ""),
        last_name=traits.get("lastName", ""),
        note=traits.get("note", ""),
        status="locked" if state == "inactive" else "",
        totp_status=totp_status,
        webauthn_status=webauthn_status,
        roles=[],
    )


class KratosUserstore:
    """Implements Userstore protocol via Kratos admin API."""

    def __init__(self, host_url: str) -> None:
        self._host_url = host_url
        self._client = httpx.AsyncClient(base_url=host_url, timeout=10.0)

    async def get_users(self) -> list[User]:
        resp = await self._client.get("/identities")
        resp.raise_for_status()
        identities = resp.json()
        return [_map_identity_to_user(i) for i in identities]

    async def get_user_by_id(self, user_id: str) -> User | None:
        try:
            resp = await self._client.get(f"/identities/{user_id}")
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
        return _map_identity_to_user(resp.json())

    async def close(self) -> None:
        await self._client.aclose()
