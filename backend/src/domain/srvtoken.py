"""SrvToken domain model — ported from Go model/srvtoken.go."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict


class SrvToken(BaseModel):
    """Represents a server authentication token with HMAC validation."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = ""
    expiration: datetime = datetime.min.replace(tzinfo=UTC)
    hash: bytes | None = None

    def validate(self, id: str) -> str | None:
        """Validate token id and expiration. Returns error string or None."""
        if self.id != id:
            return "SRV token id mismatch"
        if self.expiration < datetime.now(UTC):
            return "SRV token expired"
        return None


def _create_hash(srv_key: bytes, data: bytes) -> bytes:
    """Create HMAC-SHA3-512 hash of data using the server key."""
    return hmac.new(srv_key, data, hashlib.sha3_512).digest()


def _token_to_json(token: SrvToken) -> bytes:
    """Serialize token to JSON bytes, matching Go's json.Marshal behavior."""
    data = {"id": token.id, "expiration": token.expiration.isoformat()}
    if token.hash is not None:
        # Go encodes []byte as base64 in JSON
        data["hash"] = base64.standard_b64encode(token.hash).decode("ascii")
    else:
        data["hash"] = None
    return json.dumps(data, separators=(",", ":")).encode("utf-8")


def _token_from_json(raw: bytes) -> SrvToken:
    """Deserialize a token from JSON bytes."""
    data = json.loads(raw)
    hash_val = None
    if data.get("hash") is not None:
        hash_val = base64.standard_b64decode(data["hash"])
    return SrvToken(
        id=data["id"],
        expiration=datetime.fromisoformat(data["expiration"]),
        hash=hash_val,
    )


def new_srv_token(id: str, valid_seconds: int) -> SrvToken:
    """Create a new SrvToken with the given validity duration."""
    expiration = datetime.now(UTC) + timedelta(seconds=valid_seconds)
    return SrvToken(id=id, expiration=expiration)


def generate_srv_token(
    srv_key: bytes, id: str, valid_seconds: int
) -> tuple[str, str | None]:
    """Generate a signed, base64-encoded server token. Returns (token_str, error)."""
    token = new_srv_token(id, valid_seconds)

    # First serialization without hash for HMAC calculation
    token_bytes = _token_to_json(token)
    token.hash = _create_hash(srv_key, token_bytes)

    # Second serialization with hash included
    token_bytes = _token_to_json(token)
    encoded = base64.urlsafe_b64encode(token_bytes).decode("ascii")

    return encoded, None


def validate_srv_token(
    srv_key: bytes, id: str, encrypted_token: str
) -> str | None:
    """Validate a base64-encoded server token. Returns error string or None."""
    try:
        decoded = base64.urlsafe_b64decode(encrypted_token)
    except Exception:
        return "failed to decode token"

    try:
        token = _token_from_json(decoded)
    except Exception:
        return "failed to parse token"

    actual_hash = token.hash
    token.hash = None

    token_bytes = _token_to_json(token)
    expected_hash = _create_hash(srv_key, token_bytes)

    if not hmac.compare_digest(expected_hash, actual_hash or b""):
        return "SRV token HMAC failed validation"

    return token.validate(id)
