"""SaltAdminUserstore — user administration over the Salt relay.

Ported from server/modules/salt/saltstore.go (AddUser..SyncUsers). Every method
relays a ``manage-user`` command and raises ``SaltManageUserError`` when the
relay returns the literal ``"false"``. Authorization (Go's CheckAuthorized
calls) is handled by the service/route layer in this hexagonal codebase, not by
the adapter.
"""

from __future__ import annotations

import uuid
from itertools import count
from typing import Protocol

from src.adapters.salt.relay import SaltRelayClient
from src.domain.user import User
from src.ports.users import Userstore

# Go raises errors.New("ERROR_SALT_MANAGE_USER") when the relay returns the
# literal "false" for any manage-user command.
ERROR_SALT_MANAGE_USER = "ERROR_SALT_MANAGE_USER"


class SaltManageUserError(Exception):
    """Raised when the relay rejects a manage-user command (output == "false")."""

    def __init__(self, message: str = ERROR_SALT_MANAGE_USER) -> None:
        super().__init__(message)


class _Rolestore(Protocol):
    """The reload seam — StaticRbacAuthorizer.scan_now() (Go Rolestore.Reload())."""

    def scan_now(self) -> None: ...


class SaltAdminUserstore:
    """Administer users by relaying manage-user commands.

    Email-bearing operations look the email up from the injected ``Userstore``
    by user id (Go ``lookupEmailFromId``). After successful add/role mutations
    the role map is reloaded via ``rolestore.scan_now()`` (Go Rolestore.Reload).

    The command_id approach mirrors ``SaltGridMembersstore``: an optional
    ``request_id`` (the route/service layer will supply a real one later) with a
    per-call counter so concurrent commands never collide on the relay's
    file-queue keys.
    """

    def __init__(
        self,
        relay: SaltRelayClient,
        userstore: Userstore,
        rolestore: _Rolestore,
        *,
        request_id: str | None = None,
    ) -> None:
        self._relay = relay
        self._userstore = userstore
        self._rolestore = rolestore
        self._request_id = request_id or uuid.uuid4().hex
        self._counter = count()

    def _command_id(self, command: str) -> str:
        suffix = next(self._counter)
        if suffix == 0:
            return f"{self._request_id}_{command}"
        return f"{self._request_id}-{suffix}_{command}"

    async def _lookup_email_from_id(self, user_id: str) -> str:
        """Mirror Go lookupEmailFromId: email only on an exact id match."""
        user = await self._userstore.get_user_by_id(user_id)
        if user is not None and user.id == user_id:
            return user.email
        return ""

    async def _manage_user(self, args: dict[str, str]) -> None:
        output = await self._relay.exec_command(self._command_id("manage-user"), args)
        if output == "false":
            raise SaltManageUserError

    async def add_user(self, user: User) -> None:
        args = {
            "command": "manage-user",
            "operation": "add",
            "email": user.email,
        }
        if user.roles:
            args["role"] = user.roles[0]
        args["firstName"] = user.first_name
        args["lastName"] = user.last_name
        args["note"] = user.note
        # KNOWN GAP: the User domain model has no `password` field yet, and
        # Pydantic (extra="ignore") drops any incoming password, so this getattr
        # always yields "" — add_user therefore always relays password="". Go
        # reads user.Password; the getattr is kept so a future User.password
        # field (or model/route that carries a real password) is picked up
        # transparently without touching this adapter.
        args["password"] = getattr(user, "password", "")
        # Go calls Rolestore.Reload() AFTER err is set and BEFORE return
        # (saltstore.go:1277) — i.e. it reloads even when output=="false" or
        # the relay itself errored. Mirror that with finally so scan_now runs on
        # success, on the SaltManageUserError path, and on SaltRelayDown.
        try:
            await self._manage_user(args)
        finally:
            self._rolestore.scan_now()

    async def delete_user(self, user_id: str) -> None:
        await self._manage_user(
            {
                "command": "manage-user",
                "operation": "delete",
                "email": await self._lookup_email_from_id(user_id),
            }
        )

    async def update_profile(self, user: User) -> None:
        await self._manage_user(
            {
                "command": "manage-user",
                "operation": "profile",
                "email": await self._lookup_email_from_id(user.id),
                "firstName": user.first_name,
                "lastName": user.last_name,
                "note": user.note,
            }
        )

    async def reset_password(self, user_id: str, password: str) -> None:
        await self._manage_user(
            {
                "command": "manage-user",
                "operation": "password",
                "email": await self._lookup_email_from_id(user_id),
                "password": password,
            }
        )

    async def enable_user(self, user_id: str) -> None:
        await self._manage_user(
            {
                "command": "manage-user",
                "operation": "enable",
                "email": await self._lookup_email_from_id(user_id),
            }
        )

    async def disable_user(self, user_id: str) -> None:
        await self._manage_user(
            {
                "command": "manage-user",
                "operation": "disable",
                "email": await self._lookup_email_from_id(user_id),
            }
        )

    async def add_role(self, user_id: str, role: str, bypass_auth_check: bool = False) -> None:
        # bypass_auth_check matches the AdminUserstore protocol signature; the
        # adapter performs no authorization, so it has no behavioral effect here.
        args = {
            "command": "manage-user",
            "operation": "addrole",
            "email": await self._lookup_email_from_id(user_id),
            "role": role,
        }
        # Go reloads after err is set, before return (saltstore.go:1403): reload
        # even when output=="false" or the relay errored — mirror with finally.
        try:
            await self._manage_user(args)
        finally:
            self._rolestore.scan_now()

    async def delete_role(self, user_id: str, role: str) -> None:
        args = {
            "command": "manage-user",
            "operation": "delrole",
            "email": await self._lookup_email_from_id(user_id),
            "role": role,
        }
        # Go reloads after err is set, before return (saltstore.go:1425): reload
        # even when output=="false" or the relay errored — mirror with finally.
        try:
            await self._manage_user(args)
        finally:
            self._rolestore.scan_now()

    async def sync_users(self) -> None:
        await self._manage_user({"command": "manage-user", "operation": "sync"})
