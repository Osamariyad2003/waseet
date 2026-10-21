"""The development stub.

Two things matter here: that it behaves predictably enough to demonstrate
the product, and that it can never be mistaken for a real judgment — it says
so in every piece of reasoning it writes, and production refuses to boot
with it enabled.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.config import Settings
from app.domain.enums import SettlementAction, Verdict
from app.integrations.ai.interface import AIGateway, DealContext, DeliverableContext
from app.integrations.ai.stub import STUB_NOTICE, StubAIGateway
from app.integrations.content.interface import FetchedContent

DEAL = DealContext(
    description=(
        "Design a logo for a coffee shop, delivered as an SVG vector file with a "
        "transparent background."
    ),
    amount=Decimal("250.00"),
    currency="USD",
)
CRITERIA = (
    ("c1", "The deliverable is supplied in vector format (SVG or AI)."),
    ("c2", "The background is transparent."),
)


@pytest.fixture
def stub() -> StubAIGateway:
    return StubAIGateway()


def test_the_stub_satisfies_the_gateway_protocol(stub):
    """It has to be a drop-in, or it proves nothing about the real path."""
    assert isinstance(stub, AIGateway)


class TestItCannotPassForReal:
    async def test_every_verification_says_no_model_was_called(self, stub):
        judgment = await stub.verify_deliverable(
            deal=DEAL,
            criteria=CRITERIA,
            deliverable=DeliverableContext(type="url", content_ref="logo.svg"),
        )
        assert STUB_NOTICE in judgment.reasoning

    async def test_a_failing_verification_says_so_too(self, stub):
        judgment = await stub.verify_deliverable(
            deal=DEAL,
            criteria=CRITERIA,
            deliverable=DeliverableContext(type="url", content_ref="logo.png"),
        )
        assert STUB_NOTICE in judgment.reasoning

    async def test_mediation_says_so(self, stub):
        recommendation = await stub.mediate_dispute(
            deal=DEAL, criteria=CRITERIA, deliverable=None, verification=None
        )
        assert STUB_NOTICE in recommendation.reasoning

    def test_production_refuses_to_boot_with_the_stub_enabled(self):
        with pytest.raises(ValueError, match="USE_STUB_AI cannot be enabled in production"):
            Settings(
                environment="production",
                use_stub_ai=True,
                jwt_secret="a-production-secret-long-enough-for-hs256",
                database_url="postgresql+asyncpg://user:pass@db:5432/waseet",
            )

    def test_it_is_off_unless_asked_for(self):
        settings = Settings(database_url="sqlite+aiosqlite:///:memory:")
        assert settings.use_stub_ai is False


class TestCriteriaDrafting:
    async def test_it_draws_criteria_from_what_the_description_mentions(self, stub):
        criteria = await stub.draft_criteria(deal=DEAL)
        texts = " ".join(criterion.text for criterion in criteria)

        assert "vector" in texts
        assert "transparent" in texts.lower()

    async def test_it_always_produces_something_checkable(self, stub):
        """Even for a description with no recognisable attributes."""
        criteria = await stub.draft_criteria(
            deal=DealContext(
                description="Do the thing we discussed on the call.",
                amount=Decimal("50.00"),
                currency="USD",
            )
        )
        assert len(criteria) >= 2
        assert all(criterion.text.strip() for criterion in criteria)

    async def test_it_stays_within_a_sensible_number(self, stub):
        criteria = await stub.draft_criteria(
            deal=DealContext(
                description=(
                    "A responsive logo in vector SVG with a transparent background, "
                    "plus documentation in the repo and an Arabic translation."
                ),
                amount=Decimal("500.00"),
                currency="USD",
            )
        )
        assert 2 <= len(criteria) <= 4

    async def test_it_is_deterministic(self, stub):
        first = await stub.draft_criteria(deal=DEAL)
        second = await stub.draft_criteria(deal=DEAL)
        assert [c.text for c in first] == [c.text for c in second]


class TestVerification:
    @pytest.mark.parametrize(
        "content_ref",
        [
            "https://files.example.com/logo.svg",
            "https://github.com/acme/logo",
            "The finished copy, ready to publish.",
        ],
    )
    async def test_a_clean_submission_passes_above_the_release_threshold(self, stub, content_ref):
        judgment = await stub.verify_deliverable(
            deal=DEAL,
            criteria=CRITERIA,
            deliverable=DeliverableContext(type="url", content_ref=content_ref),
        )
        assert judgment.verdict is Verdict.PASS
        assert judgment.confidence >= Decimal("0.8")
        assert judgment.failed_criteria_count == 0

    @pytest.mark.parametrize(
        "content_ref",
        [
            "https://files.example.com/logo.png",
            "https://files.example.com/logo.JPG",
            "a draft of the logo",
            "placeholder for now",
        ],
    )
    async def test_a_submission_with_a_fail_marker_fails(self, stub, content_ref):
        judgment = await stub.verify_deliverable(
            deal=DEAL,
            criteria=CRITERIA,
            deliverable=DeliverableContext(type="url", content_ref=content_ref),
        )
        assert judgment.verdict is Verdict.FAIL
        assert judgment.failed_criteria_count == len(CRITERIA)

    async def test_a_raster_file_fetched_from_a_plain_url_still_fails(self, stub):
        """The marker is in the retrieved media type, not the URL."""
        judgment = await stub.verify_deliverable(
            deal=DEAL,
            criteria=CRITERIA,
            deliverable=DeliverableContext(
                type="url",
                content_ref="https://files.example.com/download?id=42",
                inspected=FetchedContent(kind="image", image_base64="x", media_type="image/png"),
            ),
        )
        assert judgment.verdict is Verdict.FAIL

    async def test_a_deliverable_that_could_not_be_retrieved_fails_at_low_confidence(self, stub):
        """Matching the real verifier: it has not seen the work."""
        judgment = await stub.verify_deliverable(
            deal=DEAL,
            criteria=CRITERIA,
            deliverable=DeliverableContext(
                type="url",
                content_ref="https://files.example.com/gone",
                inspected=FetchedContent.unavailable("the link returned HTTP 404"),
            ),
        )
        assert judgment.verdict is Verdict.FAIL
        assert judgment.confidence < Decimal("0.8")
        assert "could not be retrieved" in judgment.reasoning

    async def test_it_reports_on_every_confirmed_criterion(self, stub):
        judgment = await stub.verify_deliverable(
            deal=DEAL,
            criteria=CRITERIA,
            deliverable=DeliverableContext(type="url", content_ref="logo.svg"),
        )
        assert {item.criterion_id for item in judgment.per_criterion} == {"c1", "c2"}
        assert all(item.note for item in judgment.per_criterion)

    async def test_no_criteria_is_inconclusive(self, stub):
        judgment = await stub.verify_deliverable(
            deal=DEAL,
            criteria=(),
            deliverable=DeliverableContext(type="text", content_ref="done"),
        )
        assert judgment.verdict is Verdict.INCONCLUSIVE

    async def test_the_fetched_page_is_searched_too(self, stub):
        judgment = await stub.verify_deliverable(
            deal=DEAL,
            criteria=CRITERIA,
            deliverable=DeliverableContext(
                type="url",
                content_ref="https://files.example.com/work",
                inspected=FetchedContent(
                    kind="text", text="This is a draft and not finished.", media_type="text/plain"
                ),
            ),
        )
        assert judgment.verdict is Verdict.FAIL


class TestMediation:
    async def test_it_recommends_refund_when_criteria_were_unmet(self, stub):
        failed = await stub.verify_deliverable(
            deal=DEAL,
            criteria=CRITERIA,
            deliverable=DeliverableContext(type="url", content_ref="logo.png"),
        )
        recommendation = await stub.mediate_dispute(
            deal=DEAL,
            criteria=CRITERIA,
            deliverable=DeliverableContext(type="url", content_ref="logo.png"),
            verification=failed,
        )
        assert recommendation.recommendation is SettlementAction.REFUND

    async def test_it_recommends_release_when_nothing_was_unmet(self, stub):
        passed = await stub.verify_deliverable(
            deal=DEAL,
            criteria=CRITERIA,
            deliverable=DeliverableContext(type="url", content_ref="logo.svg"),
        )
        recommendation = await stub.mediate_dispute(
            deal=DEAL,
            criteria=CRITERIA,
            deliverable=DeliverableContext(type="url", content_ref="logo.svg"),
            verification=passed,
        )
        assert recommendation.recommendation is SettlementAction.RELEASE

    async def test_nothing_delivered_recommends_a_refund(self, stub):
        recommendation = await stub.mediate_dispute(
            deal=DEAL, criteria=CRITERIA, deliverable=None, verification=None
        )
        assert recommendation.recommendation is SettlementAction.REFUND

    async def test_it_never_proposes_a_split_amount_it_cannot_justify(self, stub):
        recommendation = await stub.mediate_dispute(
            deal=DEAL, criteria=CRITERIA, deliverable=None, verification=None
        )
        assert recommendation.suggested_seller_amount is None
