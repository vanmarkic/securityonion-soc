"""Tests for SrvToken domain model — ported from Go model/srvtoken_test.go."""

import base64
import json

from src.domain.srvtoken import (
    SrvToken,
    generate_srv_token,
    new_srv_token,
    validate_srv_token,
)


class TestStructValidity:
    """Ported from TestStructValidity in srvtoken_test.go."""

    def test_validate_matching_id(self):
        token = new_srv_token("foo", 200)
        err = token.validate("foo")
        assert err is None

    def test_validate_mismatched_id(self):
        token = new_srv_token("foo", 200)
        err = token.validate("bar")
        assert err == "SRV token id mismatch"


class TestFullValidity:
    """Ported from TestFullValidity in srvtoken_test.go."""

    def test_generate_and_validate(self):
        key = b"testkey"
        token_str, err = generate_srv_token(key, "myId", 60)
        assert err is None
        assert len(token_str) > 100

        err = validate_srv_token(key, "myId", token_str)
        assert err is None

    def test_mismatched_id(self):
        key = b"testkey"
        token_str, _ = generate_srv_token(key, "myId", 60)

        err = validate_srv_token(key, "myId2", token_str)
        assert err == "SRV token id mismatch"

    def test_expired_token(self):
        key = b"testkey"
        # Generate a token that's already expired (0 seconds validity)
        token_str, _ = generate_srv_token(key, "myId", -1)

        err = validate_srv_token(key, "myId", token_str)
        assert err == "SRV token expired"

    def test_different_key(self):
        key = b"testkey"
        token_str, _ = generate_srv_token(key, "myId", 60)

        key2 = b"testkey2"
        err = validate_srv_token(key2, "myId", token_str)
        assert err == "SRV token HMAC failed validation"

    def test_manipulated_token(self):
        key = b"testkey"
        token_str, _ = generate_srv_token(key, "myId", 60)

        # Decode, manipulate the id, re-encode
        decoded = base64.urlsafe_b64decode(token_str)
        manipulated = decoded.decode("utf-8").replace("myId", "byId", 1)
        encoded = base64.urlsafe_b64encode(manipulated.encode("utf-8")).decode("ascii")

        err = validate_srv_token(key, "myId", encoded)
        assert err == "SRV token HMAC failed validation"
