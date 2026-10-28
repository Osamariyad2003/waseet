"""Request and response models. Pydantic validates every external input here,
at the edge, before anything reaches a service.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

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

    # Itemized audit view, derived from per_criterion so there is a single
    # source of truth. The conditions the verifier found met vs. the ones it
    # found unmet or missing — a clearer audit artifact than the raw list.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def verified_criteria(self) -> list[str]:
        return [str(c.get("text", "")) for c in self.per_criterion if c.get("pass")]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def unmet_or_missing_criteria(self) -> list[str]:
        return [str(c.get("text", "")) for c in self.per_criterion if not c.get("pass")]


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


# --- proof-of-escrow certificate -------------------------------------------


class CertificateResponse(BaseModel):
    """A public, shareable proof that a deal was settled, and how.

    Deliberately minimal and privacy-safe: no emails, no PayPal ids, no
    descriptions — only the title, the amount, the final outcome and the AI
    verifier's audit summary. Anyone with the link can check a deal's seal
    without signing in, the way a certificate is meant to be verifiable.
    """

    deal_id: uuid.UUID
    seal: str
    title: str
    amount: Decimal
    currency: str
    outcome: str  # released | refunded | split
    state: DealState
    created_at: datetime
    # The verification block is present when the deal was AI-verified; a deal
    # settled purely by a reviewer may have no report.
    verdict: Verdict | None = None
    confidence: Decimal | None = None
    reasoning: str | None = None
    verified_criteria: list[str] = Field(default_factory=list)
    unmet_or_missing_criteria: list[str] = Field(default_factory=list)
    decided_by: DecidedBy | None = None
    decided_at: datetime | None = None
    advisory_notice: str = (
        "This certificate records an AI-verified escrow outcome on the PayPal "
        "sandbox. The verdict is advisory; a human reviewer resolves any dispute."
    )


# --- marketplace offers ----------------------------------------------------


class OfferResponse(ORMModel):
    id: uuid.UUID
    title: str
    description: str
    category: str
    amount: Decimal
    currency: str
    active: bool
    created_at: datetime
    seller: UserResponse


class CreateOfferRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5_000)
    category: str = Field(default="other", max_length=40)
    amount: Money
    currency: str = Field(min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()


# --- product catalog (Shop & Escrow) ---------------------------------------


class CatalogProductResponse(BaseModel):
    """A product from the catalog, flattened for the Shop grid and for
    pre-filling a new deal. Reference data only — no money moves here."""

    id: str
    title: str
    brand: str | None = None
    description: str | None = None
    image_url: str | None = None
    price: Decimal | None = None
    currency: str
    available: bool
    buy_url: str | None = None


# --- milestones ------------------------------------------------------------


class MilestoneSpecRequest(BaseModel):
    """One milestone the buyer asks for when creating a milestone deal."""

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5_000)
    amount: Money


class MilestoneResponse(ORMModel):
    id: uuid.UUID
    position: int
    title: str
    description: str
    amount: Decimal
    state: DealState
    payout_batch_id: str | None
    platform_fee: Decimal | None
    criteria: list[CriterionResponse] = Field(default_factory=list)
    deliverables: list[DeliverableResponse] = Field(default_factory=list)
    verification_reports: list[VerificationReportResponse] = Field(default_factory=list)


class MilestoneVerificationResultResponse(BaseModel):
    milestone: MilestoneResponse
    released: bool
    policy_outcome: str
    policy_reason: str
    advisory_notice: str = (
        "This verdict is produced by an AI verifier and is advisory. Either party "
        "can contest it, and a human reviewer resolves any dispute."
    )


class MilestoneDisputeResultResponse(BaseModel):
    """What the reviewer's decision on a milestone did."""

    milestone: MilestoneResponse
    action: SettlementAction
    to_seller: Decimal
    to_buyer: Decimal
    platform_fee: Decimal
    paypal_reference: str | None
    already_settled: bool


# --- payout tracking (PayPal Payouts API) ----------------------------------


class PayoutItemStatusResponse(ORMModel):
    transaction_id: str | None
    transaction_status: str
    amount: Decimal
    currency: str
    receiver: str


class PayoutStatusResponse(ORMModel):
    payout_batch_id: str
    batch_status: str
    amount: Decimal | None
    currency: str | None
    time_created: str | None
    items: list[PayoutItemStatusResponse] = Field(default_factory=list)


class PayoutViewResponse(BaseModel):
    """One payout batch for a deal, with its live PayPal status (or why it
    could not be read)."""

    source: str
    milestone_id: uuid.UUID | None = None
    status: PayoutStatusResponse | None = None
    error: str | None = None


class ActivityEntryResponse(ORMModel):
    """One step of a deal's PayPal money trail with its live status."""

    kind: str
    label: str
    reference_id: str
    status: str
    amount: Decimal | None
    currency: str | None
    receiver: str | None
    error: str | None


# --- deals -----------------------------------------------------------------


class CreateDealRequest(BaseModel):
    seller_email: EmailStr
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=20, max_length=5_000)
    # Optional when `milestones` is given: the deal amount is then the sum of
    # the milestone amounts, computed server-side.
    amount: Money | None = None
    currency: str = Field(min_length=3, max_length=3)
    # Two or more makes this a milestone deal; omitted or empty is a simple one.
    milestones: list[MilestoneSpecRequest] = Field(default_factory=list)

    @field_validator("currency")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()

    @field_validator("milestones")
    @classmethod
    def _enough_milestones(cls, value: list[MilestoneSpecRequest]) -> list[MilestoneSpecRequest]:
        if value and len(value) < 2:
            raise ValueError("a milestone deal needs at least two milestones")
        return value

    @model_validator(mode="after")
    def _amount_or_milestones(self) -> CreateDealRequest:
        # A simple deal must state its amount; a milestone deal derives it.
        if self.amount is None and not self.milestones:
            raise ValueError("amount is required unless milestones are provided")
        return self


class DealSummaryResponse(ORMModel):
    id: uuid.UUID
    title: str
    state: DealState
    amount: Decimal
    currency: str
    created_at: datetime
    updated_at: datetime


class DealSummaryWithParties(DealSummaryResponse):
    """The grid shows who is on each side, so the reviewer can scan at a
    glance without opening every deal."""

    buyer: UserResponse
    seller: UserResponse


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
    milestones: list[MilestoneResponse] = Field(default_factory=list)


class DealWithTimelineResponse(DealResponse):
    """The deal-timeline hero reads this in one request."""

    timeline: list[AuditEntryResponse] = Field(default_factory=list)


# --- funding ---------------------------------------------------------------


class CreateOrderResponse(BaseModel):
    paypal_order_id: str
    approve_url: str | None = None


class ClientTokenResponse(BaseModel):
    """A browser-safe token for the PayPal JS SDK v6, and the environment's
    SDK core URL so the browser loads the matching sandbox/live SDK."""

    client_token: str
    sdk_url: str


# --- reviewer dashboard ----------------------------------------------------


class StatTile(BaseModel):
    """One KPI on the reviewer dashboard."""

    key: str
    count: int
    amount: Decimal
    currency: str


class ReviewerOverviewResponse(BaseModel):
    """Everything the reviewer dashboard needs, in one call: the KPI tiles
    and every deal for the grid."""

    held_in_escrow: StatTile
    open_disputes: StatTile
    released: StatTile
    refunded: StatTile
    deals: list[DealSummaryWithParties]


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


# --- wallet / explore / account / home -------------------------------------


class WalletOverviewResponse(BaseModel):
    """Aggregated financial overview for the user's wallet."""

    held: StatTile
    released: StatTile
    refunded: StatTile
    pending: StatTile
    deals: list[DealSummaryResponse]


class LifecycleStep(BaseModel):
    step: int
    key: str
    title: str
    description: str


class SafetyPillar(BaseModel):
    key: str
    title: str
    description: str


class ExplorePlatformInfo(BaseModel):
    confidence_threshold: Decimal
    platform_fee_percent: Decimal
    sandbox_mode: bool
    ai_provider: str
    supported_deliverable_types: list[DeliverableType]


class ExploreResponse(BaseModel):
    title: str
    subtitle: str
    steps: list[LifecycleStep]
    safety_pillars: list[SafetyPillar]
    platform_info: ExplorePlatformInfo
    stats: dict[str, Any]


class AccountProfileResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: Role
    paypal_account_ref: str | None
    created_at: datetime
    total_deals: int
    deals_as_buyer: int
    deals_as_seller: int
    total_transacted_volume: Decimal
    currency: str


class UpdateAccountProfileRequest(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    paypal_account_ref: str | None = Field(default=None, max_length=320)


class HomeSummaryResponse(BaseModel):
    user: UserResponse
    active_deals_count: int
    action_required_count: int
    recent_deals: list[DealSummaryResponse]

