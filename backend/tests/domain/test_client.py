"""Tests for the Client domain model — ported from Go model/client_test.go."""

from src.domain.client import Client, is_client


class TestClientVerify:
    def test_empty_client_is_valid(self):
        client = Client()
        assert client.verify() is None

    def test_id_too_long(self):
        client = Client(id="x" * 150)
        err = client.verify()
        assert err is not None
        assert "ERROR_CLIENT_ID_TOO_LONG" in str(err)

    def test_id_valid_then_name_too_long(self):
        client = Client(id="socl_bob", name="x" * 150)
        err = client.verify()
        assert err is not None
        assert "ERROR_NAME_TOO_LONG" in str(err)

    def test_note_too_long(self):
        client = Client(note="x" * 150)
        err = client.verify()
        assert err is not None
        assert "ERROR_NOTE_TOO_LONG" in str(err)

    def test_permission_too_long(self):
        client = Client(permissions=["x" * 150])
        err = client.verify()
        assert err is not None
        assert "ERROR_PERMISSION_TOO_LONG" in str(err)

    def test_valid_client(self):
        client = Client(
            id="socl_bob",
            name="Bob",
            note="Great guy, that Bob.",
            permissions=["test/read"],
        )
        assert client.verify() is None


class TestIsClient:
    def test_valid_client_id_with_suffix(self):
        assert is_client("socl_123") is True

    def test_valid_client_id_bare_prefix(self):
        assert is_client("socl_") is True

    def test_prefix_without_underscore(self):
        assert is_client("socl") is False

    def test_no_prefix(self):
        assert is_client("123") is False

    def test_empty_string(self):
        assert is_client("") is False
