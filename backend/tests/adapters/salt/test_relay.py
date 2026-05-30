"""Tests for the Salt relay seam — fake + file-queue clients."""

import json
from pathlib import Path

import pytest

from src.adapters.salt.relay import (
    FakeRelayClient,
    FileQueueRelayClient,
    SaltRelayClient,
    SaltRelayDown,
)


class TestFakeRelayClient:
    async def test_returns_canned_value_and_records_call(self):
        fake = FakeRelayClient({"manage": "ok"})
        result = await fake.exec_command("req1_manage", {"command": "manage"})
        assert result == "ok"
        assert fake.calls == [("req1_manage", {"command": "manage"})]

    async def test_unknown_command_raises(self):
        fake = FakeRelayClient({"manage": "ok"})
        with pytest.raises(KeyError):
            await fake.exec_command("req1_other", {"command": "other"})

    def test_is_a_salt_relay_client(self):
        assert isinstance(FakeRelayClient({}), SaltRelayClient)


class TestFileQueueRelayClient:
    async def test_returns_stripped_response_and_deletes_file(self, tmp_path: Path):
        queue_dir = tmp_path / "queue"
        queue_dir.mkdir()
        command_id = "req1_manage"
        response_file = queue_dir / f"{command_id}.response"
        response_file.write_text("  hello world  \n")

        client = FileQueueRelayClient(str(queue_dir))
        result = await client.exec_command(command_id, {"command": "manage"})

        assert result == "hello world"
        assert not response_file.exists()

    async def test_timeout_raises_quickly(self, tmp_path: Path):
        queue_dir = tmp_path / "queue"
        queue_dir.mkdir()
        client = FileQueueRelayClient(str(queue_dir), timeout_ms=5)
        with pytest.raises(SaltRelayDown):
            await client.exec_command("req1_manage", {"command": "manage"})

    async def test_request_file_written_with_json(self, tmp_path: Path):
        queue_dir = tmp_path / "queue"
        queue_dir.mkdir()
        command_id = "req1_manage"
        (queue_dir / f"{command_id}.response").write_text("done")

        client = FileQueueRelayClient(str(queue_dir))
        args = {"command": "manage", "minion": "node-x"}
        await client.exec_command(command_id, args)

        request_file = queue_dir / command_id
        assert request_file.exists()
        assert json.loads(request_file.read_text()) == args

    async def test_creates_queue_dir_when_missing(self, tmp_path: Path):
        queue_dir = tmp_path / "missing" / "queue"
        client = FileQueueRelayClient(str(queue_dir), timeout_ms=5)
        with pytest.raises(SaltRelayDown):
            await client.exec_command("req1_manage", {"command": "manage"})
        assert queue_dir.is_dir()

    def test_is_a_salt_relay_client(self, tmp_path: Path):
        assert isinstance(FileQueueRelayClient(str(tmp_path)), SaltRelayClient)
