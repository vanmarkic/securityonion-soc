"""UsersService -- business logic ported from Go usershandler.go."""

from __future__ import annotations

import re

from src.domain.user import User
from src.ports.roles import Rolestore
from src.ports.users import AdminUserstore, Userstore

ID_PATTERN = re.compile(r"^[A-Za-z0-9-]{36}$")
ROLE_PATTERN = re.compile(r"^[A-Za-z0-9-_]{3,50}$")


class InvalidId(Exception):
    pass


class InvalidRole(Exception):
    pass


class InvalidToggle(Exception):
    pass


class ValidationError(Exception):
    pass


class UsersService:
    """Business logic for user CRUD, roles, and sync."""

    def __init__(
        self,
        userstore: Userstore,
        admin_userstore: AdminUserstore,
        rolestore: Rolestore,
    ) -> None:
        self._userstore = userstore
        self._admin_userstore = admin_userstore
        self._rolestore = rolestore

    # ------------------------------------------------------------------
    # GET
    # ------------------------------------------------------------------

    async def get_users(self) -> list[User]:
        await self._rolestore.ensure_default_role_for_user()
        return await self._userstore.get_users()

    # ------------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------------

    async def create_user(self, user: User) -> User:
        err = user.verify()
        if err is not None:
            raise ValidationError(err)
        await self._admin_userstore.add_user(user)
        return user

    # ------------------------------------------------------------------
    # ROLE MANAGEMENT
    # ------------------------------------------------------------------

    async def add_role(self, user_id: str, role: str) -> None:
        if not ID_PATTERN.match(user_id):
            raise InvalidId("Invalid id")
        if not ROLE_PATTERN.match(role):
            raise InvalidRole("Invalid role")
        await self._admin_userstore.add_role(user_id, role, False)

    async def delete_role(self, user_id: str, role: str) -> None:
        if not ID_PATTERN.match(user_id):
            raise InvalidId("Invalid id")
        if not ROLE_PATTERN.match(role):
            raise InvalidRole("Invalid role")
        await self._admin_userstore.delete_role(user_id, role)

    # ------------------------------------------------------------------
    # SYNC
    # ------------------------------------------------------------------

    async def sync_users(self) -> None:
        await self._admin_userstore.sync_users()

    # ------------------------------------------------------------------
    # UPDATE PROFILE
    # ------------------------------------------------------------------

    async def update_profile(self, user_id: str, user: User) -> User:
        user.id = user_id
        err = user.verify()
        if err is not None:
            raise ValidationError(err)
        await self._admin_userstore.update_profile(user)
        return user

    # ------------------------------------------------------------------
    # RESET PASSWORD
    # ------------------------------------------------------------------

    async def reset_password(self, user_id: str, password: str) -> None:
        if not ID_PATTERN.match(user_id):
            raise InvalidId("Invalid id")
        await self._admin_userstore.reset_password(user_id, password)

    # ------------------------------------------------------------------
    # TOGGLE ENABLE/DISABLE
    # ------------------------------------------------------------------

    async def toggle_user(self, user_id: str, toggle: str) -> None:
        if not ID_PATTERN.match(user_id):
            raise InvalidId("Invalid id")
        action = toggle.lower()
        if action == "enable":
            await self._admin_userstore.enable_user(user_id)
        elif action == "disable":
            await self._admin_userstore.disable_user(user_id)
        else:
            raise InvalidToggle("Invalid toggle action")

    # ------------------------------------------------------------------
    # DELETE
    # ------------------------------------------------------------------

    async def delete_user(self, user_id: str) -> None:
        if not ID_PATTERN.match(user_id):
            raise InvalidId("Invalid id")
        await self._admin_userstore.delete_user(user_id)
