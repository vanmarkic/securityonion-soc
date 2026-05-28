"""ClientsService -- business logic ported from Go clientshandler.go."""

from __future__ import annotations

import re

from src.domain.client import Client
from src.ports.clients import AdminClientstore, Clientstore

CLIENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_]{6,55}$")
PERMISSION_PATTERN = re.compile(r"^[a-z]+/[a-z_]+$")


class InvalidClientId(Exception):
    pass


class InvalidPermission(Exception):
    pass


class ValidationError(Exception):
    pass


class ClientsService:
    """Business logic for client CRUD, permissions, and secret management."""

    def __init__(
        self,
        clientstore: Clientstore,
        admin_clientstore: AdminClientstore,
    ) -> None:
        self._clientstore = clientstore
        self._admin_clientstore = admin_clientstore

    # ------------------------------------------------------------------
    # GET
    # ------------------------------------------------------------------

    async def get_clients(self) -> list[Client]:
        return await self._clientstore.get_clients()

    # ------------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------------

    async def create_client(self, client: Client) -> Client:
        err = client.verify()
        if err is not None:
            raise ValidationError(err)
        return await self._admin_clientstore.add_client(client)

    # ------------------------------------------------------------------
    # ADD PERMISSION
    # ------------------------------------------------------------------

    async def add_permission(self, client_id: str, resource: str, privilege: str) -> None:
        if not CLIENT_ID_PATTERN.match(client_id):
            raise InvalidClientId("Invalid id")
        permission = f"{resource}/{privilege}"
        if not PERMISSION_PATTERN.match(permission):
            raise InvalidPermission("Invalid permission")
        await self._admin_clientstore.add_client_permission(client_id, permission)

    # ------------------------------------------------------------------
    # UPDATE
    # ------------------------------------------------------------------

    async def update_client(self, client_id: str, client: Client) -> Client:
        if not CLIENT_ID_PATTERN.match(client_id):
            raise InvalidClientId("Invalid id")
        client.id = client_id
        err = client.verify()
        if err is not None:
            raise ValidationError(err)
        await self._admin_clientstore.update_client(client)
        return client

    # ------------------------------------------------------------------
    # REGENERATE SECRET
    # ------------------------------------------------------------------

    async def generate_secret(self, client_id: str) -> Client:
        if not CLIENT_ID_PATTERN.match(client_id):
            raise InvalidClientId("Invalid id")
        return await self._admin_clientstore.generate_secret(client_id)

    # ------------------------------------------------------------------
    # DELETE
    # ------------------------------------------------------------------

    async def delete_client(self, client_id: str) -> None:
        if not CLIENT_ID_PATTERN.match(client_id):
            raise InvalidClientId("Invalid id")
        await self._admin_clientstore.delete_client(client_id)

    # ------------------------------------------------------------------
    # DELETE PERMISSION
    # ------------------------------------------------------------------

    async def delete_permission(self, client_id: str, resource: str, privilege: str) -> None:
        if not CLIENT_ID_PATTERN.match(client_id):
            raise InvalidClientId("Invalid id")
        permission = f"{resource}/{privilege}"
        if not PERMISSION_PATTERN.match(permission):
            raise InvalidPermission("Invalid permission")
        await self._admin_clientstore.delete_client_permission(client_id, permission)
