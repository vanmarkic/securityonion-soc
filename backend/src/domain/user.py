"""User domain model."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class User(BaseModel):
    """Represents a Security Onion user."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    email: str
    first_name: str = Field(alias="firstName")
    last_name: str = Field(alias="lastName")
    note: str
    roles: list[str]
    status: str
    totp_status: str = Field(alias="totpStatus")
    webauthn_status: str = Field(alias="webauthnStatus")
