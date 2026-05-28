"""Tests for the Authorizer port and Unauthorized exception."""

import pytest

from src.ports.auth import Authorizer, Unauthorized


class FakeAuthorizer:
    """A fake that satisfies the Authorizer protocol."""

    def __init__(self, allow: bool = True):
        self._allow = allow

    async def check_authorized(self, user_id: str, operation: str, resource: str) -> None:
        if not self._allow:
            raise Unauthorized(user_id=user_id, operation=operation, resource=resource)


class TestUnauthorized:
    def test_exception_attributes(self):
        exc = Unauthorized(user_id="u1", operation="read", resource="info")
        assert exc.user_id == "u1"
        assert exc.operation == "read"
        assert exc.resource == "info"

    def test_exception_message(self):
        exc = Unauthorized(user_id="u1", operation="read", resource="info")
        assert "u1" in str(exc)
        assert "read" in str(exc)
        assert "info" in str(exc)

    def test_exception_is_exception(self):
        exc = Unauthorized(user_id="u1", operation="read", resource="info")
        assert isinstance(exc, Exception)


class TestAuthorizer:
    def test_fake_satisfies_protocol(self):
        authorizer: Authorizer = FakeAuthorizer()
        assert isinstance(authorizer, Authorizer)

    async def test_authorized_passes(self):
        authorizer: Authorizer = FakeAuthorizer(allow=True)
        # Should not raise
        await authorizer.check_authorized("u1", "read", "info")

    async def test_unauthorized_raises(self):
        authorizer: Authorizer = FakeAuthorizer(allow=False)
        with pytest.raises(Unauthorized) as exc_info:
            await authorizer.check_authorized("u1", "read", "info")
        assert exc_info.value.user_id == "u1"
