"""Tests for parse_members — ported from Go TestGetMembersFromJson."""

import json

import pytest

from src.adapters.salt.members import parse_members
from src.domain.gridmember import (
    GRID_MEMBER_ACCEPTED,
    GRID_MEMBER_DENIED,
    GRID_MEMBER_REJECTED,
    GRID_MEMBER_UNACCEPTED,
)


class TestParseMembers:
    def test_parses_accepted_minion(self):
        # Mirrors Go TestGetMembersFromJson "Good parse".
        output = json.dumps({"minions": {"minion_id": "fingerprint"}})

        members = parse_members(output)

        assert len(members) == 1
        member = members[0]
        assert member.id == "minion_id"
        assert member.name == "minion"
        assert member.role == "id"
        assert member.fingerprint == "fingerprint"
        assert member.status == GRID_MEMBER_ACCEPTED

    def test_maps_each_bucket_to_its_status(self):
        output = json.dumps(
            {
                "minions": {"a_sensor": "fp-a"},
                "minions_pre": {"b_sensor": "fp-b"},
                "minions_rejected": {"c_sensor": "fp-c"},
                "minions_denied": {"d_sensor": "fp-d"},
            }
        )

        members = parse_members(output)

        by_id = {m.id: m for m in members}
        assert by_id["a_sensor"].status == GRID_MEMBER_ACCEPTED
        assert by_id["b_sensor"].status == GRID_MEMBER_UNACCEPTED
        assert by_id["c_sensor"].status == GRID_MEMBER_REJECTED
        assert by_id["d_sensor"].status == GRID_MEMBER_DENIED

    def test_malformed_json_raises(self):
        # Mirrors Go "Parse error" on []byte("{ds").
        with pytest.raises(json.JSONDecodeError):
            parse_members("{ds")

    def test_empty_object_returns_empty_list(self):
        assert parse_members("{}") == []
