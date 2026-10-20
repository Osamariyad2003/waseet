"""SQLAlchemy ORM models.

Importing this package registers every mapper on `Base.metadata`, which is
what Alembic autogenerate and the test schema creation both rely on.
"""

from app.models.audit import AuditLogEntry
from app.models.deal import AcceptanceCriterion, Deal
from app.models.deliverable import Deliverable
from app.models.user import User
from app.models.verification import VerificationReport
from app.models.webhook import WebhookEvent

__all__ = [
    "AcceptanceCriterion",
    "AuditLogEntry",
    "Deal",
    "Deliverable",
    "User",
    "VerificationReport",
    "WebhookEvent",
]
