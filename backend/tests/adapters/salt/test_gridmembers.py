"""Tests for SaltGridMembersstore — list-minions + manage-minion via the relay."""

import json

import pytest

from src.adapters.salt.gridmembers import SaltGridMembersstore
from src.adapters.salt.relay import FakeRelayClient
from src.domain.gridmember import GRID_MEMBER_ACCEPTED
from src.ports.gridmembers import GridMembersstore

_LIST_MINIONS_JSON = json.dumps({"minions": {"sensor_id": "fingerprint"}})


class TestSatisfiesPort:
    def test_is_a_gridmembersstore(self):
        store = SaltGridMembersstore(FakeRelayClient({}))
        assert isinstance(store, GridMembersstore)


class TestGetMembers:
    async def test_parses_list_minions_output(self):
        fake = FakeRelayClient({"list-minions": _LIST_MINIONS_JSON})
        store = SaltGridMembersstore(fake)

        members = await store.get_members()

        assert len(members) == 1
        assert members[0].id == "sensor_id"
        assert members[0].name == "sensor"
        assert members[0].role == "id"
        assert members[0].fingerprint == "fingerprint"
        assert members[0].status == GRID_MEMBER_ACCEPTED

    async def test_sends_list_minions_command(self):
        fake = FakeRelayClient({"list-minions": _LIST_MINIONS_JSON})
        store = SaltGridMembersstore(fake)

        await store.get_members()

        assert len(fake.calls) == 1
        _command_id, args = fake.calls[0]
        assert args == {"command": "list-minions"}

    async def test_false_output_raises(self):
        fake = FakeRelayClient({"list-minions": "false"})
        store = SaltGridMembersstore(fake)

        with pytest.raises(Exception, match="ERROR_SALT_MANAGE_MEMBER"):
            await store.get_members()


class TestManageMember:
    async def test_sends_manage_minion_args(self):
        fake = FakeRelayClient({"manage-minion": "true"})
        store = SaltGridMembersstore(fake)

        await store.manage_member("accept", "sensor_id")

        assert len(fake.calls) == 1
        _command_id, args = fake.calls[0]
        assert args == {
            "command": "manage-minion",
            "operation": "accept",
            "id": "sensor_id",
        }

    async def test_false_output_raises(self):
        fake = FakeRelayClient({"manage-minion": "false"})
        store = SaltGridMembersstore(fake)

        with pytest.raises(Exception, match="ERROR_SALT_MANAGE_MEMBER"):
            await store.manage_member("accept", "sensor_id")


class TestCommandId:
    async def test_command_id_is_unique_per_call_and_carries_command(self):
        fake = FakeRelayClient(
            {"manage-minion": "true", "list-minions": _LIST_MINIONS_JSON}
        )
        store = SaltGridMembersstore(fake)

        await store.manage_member("accept", "a")
        await store.manage_member("accept", "b")

        ids = [command_id for command_id, _args in fake.calls]
        assert ids[0] != ids[1]
        assert all(cid.endswith("_manage-minion") for cid in ids)

    async def test_request_id_is_used_when_provided(self):
        fake = FakeRelayClient({"list-minions": _LIST_MINIONS_JSON})
        store = SaltGridMembersstore(fake, request_id="req-42")

        await store.get_members()

        command_id, _args = fake.calls[0]
        assert command_id == "req-42_list-minions"
