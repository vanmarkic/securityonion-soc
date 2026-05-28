"""Stub Userstore — in-memory adapter for development."""

from __future__ import annotations

from src.domain.user import User


class StubUserstore:
    """Returns hardcoded dev users. Satisfies the Userstore protocol."""

    def __init__(self) -> None:
        self._users = [
            User(
                id="00000000-0000-0000-0000-000000000001",
                email="admin@securityonion.local",
                first_name="Admin",
                last_name="User",
                note="",
                roles=["superuser"],
                status="active",
                totp_status="disabled",
                webauthn_status="disabled",
            ),
            User(
                id="00000000-0000-0000-0000-000000000002",
                email="analyst@securityonion.local",
                first_name="Analyst",
                last_name="User",
                note="",
                roles=["analyst"],
                status="active",
                totp_status="disabled",
                webauthn_status="disabled",
            ),
        ]

    async def get_users(self) -> list[User]:
        return list(self._users)

    async def get_user_by_id(self, user_id: str) -> User | None:
        for u in self._users:
            if u.id == user_id:
                return u
        return None
