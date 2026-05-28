"""User domain model."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

MAX_USER_ID_LEN = 36
MAX_FIRSTNAME_LEN = 100
MAX_LASTNAME_LEN = 100
MAX_NOTE_LEN = 100
MAX_ROLE_LEN = 50


class User(BaseModel):
    """Represents a Security Onion user."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = ""
    email: str = ""
    first_name: str = Field(default="", alias="firstName")
    last_name: str = Field(default="", alias="lastName")
    note: str = ""
    roles: list[str] = Field(default_factory=list)
    status: str = ""
    totp_status: str = Field(default="", alias="totpStatus")
    webauthn_status: str = Field(default="", alias="webauthnStatus")

    def verify(self) -> str | None:
        """Validate field lengths. Returns error string or None if valid."""
        if len(self.id) > MAX_USER_ID_LEN:
            return "ERROR_USER_ID_TOO_LONG"
        if len(self.first_name) > MAX_FIRSTNAME_LEN:
            return "ERROR_FIRSTNAME_TOO_LONG"
        if len(self.last_name) > MAX_LASTNAME_LEN:
            return "ERROR_LASTNAME_TOO_LONG"
        if len(self.note) > MAX_NOTE_LEN:
            return "ERROR_NOTE_TOO_LONG"
        for role in self.roles:
            if len(role) > MAX_ROLE_LEN:
                return "ERROR_ROLE_TOO_LONG"
        return None
