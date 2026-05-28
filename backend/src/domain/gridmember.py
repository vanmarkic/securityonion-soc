"""GridMember domain model — ported from Go model/gridmember.go."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

GRID_MEMBER_ACCEPTED = "accepted"
GRID_MEMBER_UNACCEPTED = "unaccepted"
GRID_MEMBER_REJECTED = "rejected"
GRID_MEMBER_DENIED = "denied"


class GridMember(BaseModel):
    """Represents a member of the Security Onion grid."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = ""
    name: str = ""
    role: str = ""
    fingerprint: str = ""
    status: str = ""


def new_grid_member(id: str, status: str, fingerprint: str) -> GridMember:
    """Create a GridMember by parsing the id into name and role.

    The id format is ``<name>_<role>`` where the last underscore-delimited
    segment is the role and everything before it is the name.
    """
    pieces = id.split("_")
    role = pieces[-1]
    name = id.removesuffix("_" + role)
    return GridMember(
        id=id,
        name=name,
        role=role,
        status=status,
        fingerprint=fingerprint,
    )
