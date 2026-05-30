"""Parse Salt ``list-minions`` JSON into GridMembers.

Ported from server/modules/salt/saltstore.go (getMembersFromJson + ListResponse).
The relay returns a JSON object with four buckets, each a mapping of
``id -> fingerprint``; the bucket determines the member's status.
"""

from __future__ import annotations

import json

from src.domain.gridmember import (
    GRID_MEMBER_ACCEPTED,
    GRID_MEMBER_DENIED,
    GRID_MEMBER_REJECTED,
    GRID_MEMBER_UNACCEPTED,
    GridMember,
    new_grid_member,
)

# Maps each ListResponse JSON key to the status it confers, mirroring Go's
# ListResponse struct tags (minions/minions_pre/minions_rejected/minions_denied).
_BUCKETS: tuple[tuple[str, str], ...] = (
    ("minions", GRID_MEMBER_ACCEPTED),
    ("minions_pre", GRID_MEMBER_UNACCEPTED),
    ("minions_rejected", GRID_MEMBER_REJECTED),
    ("minions_denied", GRID_MEMBER_DENIED),
)


def parse_members(output: str) -> list[GridMember]:
    """Parse a ``list-minions`` JSON body into GridMembers.

    Malformed JSON raises ``json.JSONDecodeError`` rather than silently
    returning an empty list, matching Go's parse-error behavior.
    """
    response = json.loads(output)

    members: list[GridMember] = []
    for key, status in _BUCKETS:
        bucket = response.get(key) or {}
        for member_id, fingerprint in bucket.items():
            members.append(new_grid_member(member_id, status, fingerprint))
    return members
