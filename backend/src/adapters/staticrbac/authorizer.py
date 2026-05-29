"""StaticRBAC — file-based role and permission management.

Ported from Go server/modules/staticrbac/staticrbacauthorizer.go.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from pathlib import Path

from src.ports.auth import Unauthorized

logger = logging.getLogger(__name__)


class StaticRbacAuthorizer:
    """Implements Authorizer and Rolestore protocols."""

    def __init__(self) -> None:
        self._role_map: dict[str, list[str]] = {}
        self._user_map: dict[str, list[str]] = {}
        self._role_files: list[str] = []
        self._user_files: list[str] = []
        self._scan_interval_ms: int = 60_000
        self._default_role: str = ""
        self._previous_role_hash: bytes = b""
        self._previous_user_hash: bytes = b""
        self._lock = threading.Lock()

    def init(
        self,
        user_files: list[str],
        role_files: list[str],
        scan_interval_ms: int,
        default_role: str,
    ) -> None:
        self._role_files = role_files
        self._user_files = user_files
        if scan_interval_ms <= 0:
            raise ValueError("scan_interval_ms must be a positive integer")
        self._scan_interval_ms = scan_interval_ms
        self._default_role = default_role
        self.scan_now()

    def scan_now(self) -> None:
        new_role_map, role_hash = self._scan_files(self._role_files)
        if role_hash != self._previous_role_hash:
            self.update_role_map(new_role_map)
            self._previous_role_hash = role_hash

        new_user_map, user_hash = self._scan_files(self._user_files)
        if user_hash != self._previous_user_hash:
            self.update_user_map(new_user_map)
            self._previous_user_hash = user_hash

    def update_role_map(self, new_map: dict[str, list[str]]) -> None:
        with self._lock:
            self._role_map = new_map

    def update_user_map(self, new_map: dict[str, list[str]]) -> None:
        with self._lock:
            self._user_map = new_map

    def is_authorized(self, subject: str, requested_permission: str) -> bool:
        if subject == requested_permission:
            return True
        permissions = self._role_map.get(subject, [])
        return any(self.is_authorized(perm, requested_permission) for perm in permissions)

    def check_user_operation_authorized(self, user_id: str, operation: str, target: str) -> None:
        permission = f"{target}/{operation}"
        with self._lock:
            roles = self._user_map.get(user_id, [])
            for role in roles:
                if self.is_authorized(role, permission):
                    return
        raise Unauthorized(user_id, operation, target)

    async def check_authorized(self, user_id: str, operation: str, resource: str) -> None:
        self.check_user_operation_authorized(user_id, operation, resource)

    def get_roles_sync(self) -> list[str]:
        perm_set: set[str] = set()
        for perms in self._role_map.values():
            perm_set.update(perms)
        roles = [r for r in self._role_map if r not in perm_set]
        return sorted(roles)

    async def get_roles(self) -> list[str]:
        return self.get_roles_sync()

    async def get_permissions(self) -> dict[str, list[str]]:
        final: dict[str, list[str]] = {}
        seen: set[str] = set()
        for perms in self._role_map.values():
            for perm in perms:
                if perm not in seen and "/" in perm:
                    resource, privilege = perm.split("/", 1)
                    final.setdefault(resource, []).append(privilege)
                    seen.add(perm)
        for v in final.values():
            v.sort()
        return final

    async def ensure_default_role_for_user(self) -> None:
        pass

    def get_roles_for_user(self, user_id: str) -> list[str]:
        with self._lock:
            return list(self._user_map.get(user_id, []))

    def add_role_to_user(self, user_id: str, role: str) -> None:
        with self._lock:
            roles = self._user_map.setdefault(user_id, [])
            if role not in roles:
                roles.append(role)
                roles.sort()

    def remove_role_from_user(self, user_id: str, role: str) -> None:
        with self._lock:
            roles = self._user_map.get(user_id, [])
            if role in roles:
                roles.remove(role)

    def _scan_files(self, files: list[str]) -> tuple[dict[str, list[str]], bytes]:
        new_map: dict[str, list[str]] = {}
        hash_text = ""
        for path in files:
            try:
                content = Path(path).read_text()
            except OSError:
                logger.error("Unable to open file: %s", path)
                continue
            for line in content.splitlines():
                hash_text += line
                self._parse_line(new_map, line)
        return new_map, hashlib.md5(hash_text.encode()).digest()

    def _parse_line(self, mp: dict[str, list[str]], line: str) -> None:
        line = line.replace(",", " ").replace(";", " ").strip()
        if not line or line.startswith("#"):
            return
        pieces = line.split(":")
        if len(pieces) < 2 or len(pieces) > 3:
            logger.warning("Invalid mapping: %s", line)
            return
        permission = pieces[0].strip()
        role_tokens = pieces[1].split()
        operation = "+" if len(pieces) <= 2 else pieces[2].strip()

        for role in role_tokens:
            role = role.strip()
            if role:
                self._adjust_map(mp, role, permission, operation)

    @staticmethod
    def _adjust_map(mp: dict[str, list[str]], subject: str, permission: str, operation: str) -> None:
        perms = mp.setdefault(subject, [])
        exists = permission in perms
        if not exists and operation == "+":
            perms.append(permission)
            perms.sort()
        elif exists and operation == "-":
            perms.remove(permission)
