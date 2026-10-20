"""Request and response models. Pydantic validates every external input here,
at the edge, before anything reaches a service.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.domain.enums import (
    Actor,
    DealState,
    DecidedBy,
    DeliverableType,
    Role,
    SettlementAction,
    Verdict,
)

Money = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- auth ------------------------------------------------------------------


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class UserResponse(ORMModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: Role


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserResponse


# --- criteria / deliverables / verification --------------------------------


class CriterionResponse(ORMModel):
    id: uuid.UUID
    text: str
    position: int
    confirmed_by_buyer: bool
    confirmed_by_seller: bool


class DeliverableResponse(ORMModel):
    id: uuid.UUID
    type: DeliverableType
    content_ref: str
    note: str | None
    submitted_at: datetime


class SubmitDeliverableRequest(BaseModel):
    type: DeliverableType
    content_ref: str = Field(min_length=1, max_length=20_000)
    note: str | None = Field(default=None, max_length=2_000)

    @field_validator("content_ref")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("the deliverable cannot be empty")
        return value


class VerificationReportResponse(ORMModel):
    id: uuid.UUID
    verdict: Verdict
    confidence: Decimal
    reasoning: str
    per_criterion: list[dict[str, Any]]
    decided_by: DecidedBy
    recommendation: str | None
    decided_at: datetime


class VerificationResultResponse(BaseModel):
    """The verification plus what the policy did with it — so the UI can show
    the decision, not just the verdict."""

    report: VerificationReportResponse
    state: DealState
    released: bool
    policy_outcome: str
    policy_reason: str
    # Stated plainly, per the SRS honesty requirement.
    advisory_notice: str = (
        "This verdict is produced by an AI verifier and is advisory. Either party "
        "can contest it, and a human reviewer resolves any dispute."
    )


# --- deals -----------------------------------------------------------------


class CreateDealRequest(BaseModel):
    seller_email: EmailStr
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=20, max_length=5_000)
    amount: Money
    currency: str = Field(min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()


class DealSummaryResponse(ORMModel):
    id: uuid.UUID
    title: str
    state: DealState
    amount: Decimal
    currency: str
    created_at: datetime
    updated_at: datetime


class AuditEntryResponse(ORMModel):
    id: uuid.UUID
    from_state: DealState | None
    to_state: DealState
    actor: Actor
    event: str
    reason: str
    paypal_reference: str | None
    created_at: datetime


class DealResponse(ORMModel):
    id: uuid.UUID
    title: str
    description: str
    state: DealState
    amount: Decimal
    currency: str
    platform_fee: Decimal | None
    buyer: UserResponse
    seller: UserResponse
    paypal_order_id: str | None
    paypal_capture_id: str | None
    payout_batch_id: str | None
    refund_id: str | None
    created_at: datetime
    updated_at: datetime
    criteria: list[CriterionResponse] = Field(default_factory=list)
    deliverables: list[DeliverableResponse] = Field(default_factory=list)
    verification_reports: list[VerificationReportResponse] = Field(default_factory=list)


class DealWithTimelineResponse(DealResponse):
    """The deal-timeline hero reads this in one request."""

    timeline: list[AuditEntryResponse] = Field(default_factory=list)


# --- funding ---------------------------------------------------------------


class CreateOrderResponse(BaseModel):
    paypal_order_id: str
    approve_url: str | None = None


class ClientTokenResponse(BaseModel):
    """A browser-safe token for the PayPal JS SDK v6."""

    client_token: str


class CaptureOrderRequest(BaseModel):
    """The order id the client approved.

    Optional: the server already knows the deal's order id and refuses a
    mismatch, so the client cannot nominate a different order.
    """

    paypal_order_id: str | None = Field(default=None, max_length=64)


# --- contest / dispute -----------------------------------------------------


class ContestRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2_000)


class MediationResponse(BaseModel):
    recommendation: SettlementAction
    reasoning: str
    suggested_seller_amount: Decimal | None = None
    advisory_notice: str = (
        "This is an AI recommendation for the reviewer. The reviewer makes the "
        "final decision and only that decision moves money."
    )


class ResolveDisputeRequest(BaseModel):
    action: SettlementAction
    reasoning: str = Field(min_length=1, max_length=5_000)
    seller_amount: Money | None = None


class ResolveDisputeResponse(BaseModel):
    state: DealState
    action: SettlementAction
    to_seller: Decimal
    to_buyer: Decimal
    platform_fee: Decimal
    paypal_reference: str | None
    already_settled: bool
