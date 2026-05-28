"""Client domain model — ported from Go model/client.go."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

API_CLIENT_PREFIX = "socl_"
MAX_CLIENT_ID_LEN = 55
MAX_CLIENT_NAME_LEN = 50
MAX_PERMISSION_LEN = 50
MAX_NOTE_LEN = 100


def is_client(id: str) -> bool:
    """Return True if the id starts with the API client prefix."""
    return id.startswith(API_CLIENT_PREFIX)


class Client(BaseModel):
    """Represents a Security Onion API client."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = ""
    name: str = ""
    secret: str = ""
    permissions: list[str] = Field(default_factory=list)
    note: str = ""
    search_username: str = Field(default="", alias="searchUsername")

    def verify(self) -> str | None:
        """Validate field lengths. Returns error string or None if valid."""
        if len(self.id) > MAX_CLIENT_ID_LEN:
            return "ERROR_CLIENT_ID_TOO_LONG"
        if len(self.name) > MAX_CLIENT_NAME_LEN:
            return "ERROR_NAME_TOO_LONG"
        if len(self.note) > MAX_NOTE_LEN:
            return "ERROR_NOTE_TOO_LONG"
        for perm in self.permissions:
            if len(perm) > MAX_PERMISSION_LEN:
                return "ERROR_PERMISSION_TOO_LONG"
        return None
