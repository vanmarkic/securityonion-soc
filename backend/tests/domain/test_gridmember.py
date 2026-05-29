"""Tests for GridMember domain model — ported from Go model/gridmember_test.go."""

from src.domain.gridmember import (
    GRID_MEMBER_ACCEPTED,
    GRID_MEMBER_DENIED,
    GRID_MEMBER_REJECTED,
    GRID_MEMBER_UNACCEPTED,
    new_grid_member,
)


class TestNewGridMember:
    """Ported from TestNewGridMember in gridmember_test.go."""

    def test_typical_use_case(self):
        member = new_grid_member("foo_bar", "rejected", "aa:bb")
        assert member.id == "foo_bar"
        assert member.name == "foo"
        assert member.role == "bar"
        assert member.fingerprint == "aa:bb"
        assert member.status == "rejected"

    def test_hostname_with_underscore(self):
        member = new_grid_member("foo_bar_car", "rejected", "aa:bb")
        assert member.id == "foo_bar_car"
        assert member.name == "foo_bar"
        assert member.role == "car"
        assert member.fingerprint == "aa:bb"
        assert member.status == "rejected"


class TestGridMemberConstants:
    def test_status_constants(self):
        assert GRID_MEMBER_ACCEPTED == "accepted"
        assert GRID_MEMBER_UNACCEPTED == "unaccepted"
        assert GRID_MEMBER_REJECTED == "rejected"
        assert GRID_MEMBER_DENIED == "denied"
