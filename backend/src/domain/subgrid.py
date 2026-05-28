"""Subgrid domain model — ported from Go model/subgrid.go."""

from __future__ import annotations

import json as _json

from pydantic import BaseModel, ConfigDict, Field

from src.domain.client import API_CLIENT_PREFIX


class Subgrid(BaseModel):
    """Represents a remote subgrid connection."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = ""
    manager_url: str = Field(default="", alias="managerUrl")
    client_id: str = Field(default="", alias="clientId")
    client_secret: str = Field(default="", alias="clientSecret")
    enabled: bool = False
    ca_certificate: str = Field(default="", alias="caCertificate")
    skip_tls_verify: bool = Field(default=False, alias="skipTlsVerify")

    def verify(self) -> str | None:
        """Validate subgrid fields. Returns error string or None if valid.

        When disabled, validation is skipped (matches Go behavior).
        """
        if not self.enabled:
            return None

        if not self.id.strip():
            return "invalid subgrid ID; must not be empty"
        if not self.manager_url.strip():
            return "invalid subgrid Manager URL; must not be empty"
        if not self.manager_url.startswith("https://"):
            return "invalid subgrid Manager URL; must specify the HTTPS protocol"
        if not self.client_id.strip():
            return "invalid subgrid client ID; must not be empty"
        if not self.client_id.startswith(API_CLIENT_PREFIX):
            return "invalid subgrid client ID; malformed client ID"
        if not self.client_secret.strip():
            return "invalid subgrid client secret; must not be empty"

        return None

    def to_json(self) -> str:
        """Serialize to JSON with client_secret masked (empty string).

        Matches Go's custom MarshalJSON behavior.
        """
        data = self.model_dump(by_alias=True)
        data["clientSecret"] = ""
        return _json.dumps(data)
