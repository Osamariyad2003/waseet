"""SQL enum types, defined exactly once.

Postgres enums are database-level types, so reusing the same type across two
tables means sharing one object — otherwise a migration tries to CREATE TYPE
twice. Everything in `app/models` imports its enum types from here.

`JSONType` lives here for the same reason: JSONB on Postgres, plain JSON
elsewhere so the unit suite can run against SQLite without a container.
"""

from __future__ import annotations

from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

from app.domain.enums import Actor, DealState, DecidedBy, DeliverableType, Role, Verdict


def _sql_enum(enum_cls: type, name: str) -> SAEnum:
    """Store the enum's *values* (e.g. "pass"), not its member names."""
    return SAEnum(enum_cls, name=name, values_callable=lambda enum: [m.value for m in enum])


deal_state_enum = _sql_enum(DealState, "deal_state")
deliverable_type_enum = _sql_enum(DeliverableType, "deliverable_type")
verdict_enum = _sql_enum(Verdict, "verdict")
decided_by_enum = _sql_enum(DecidedBy, "decided_by")
role_enum = _sql_enum(Role, "role")
actor_enum = _sql_enum(Actor, "actor")

JSONType = JSON().with_variant(JSONB(), "postgresql")
