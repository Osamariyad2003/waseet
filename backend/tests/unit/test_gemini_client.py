"""The Gemini gateway: structured-output parsing and failure handling.

The Google SDK call is stubbed; everything around it — the JSON parsing, the
shared guardrails, the transient/permanent retry mapping — is the real code.
Because the parsing lives in base.py, these mirror the Anthropic suite: the
same judgment is reached whichever provider runs it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import pytest

from app.config import Settings
from app.domain.enums import SettlementAction, Verdict
from app.integrations.ai.gemini import GeminiAIGateway
from app.integrations.ai.interface import AIGateway, DealContext, DeliverableContext
from app.integrations.content.interface import FetchedContent

DEAL = DealContext(
    description="Design a logo for a coffee shop, delivered as a vector file.",
    amount=Decimal("250.00"),
    currency="USD",
)
CRITERIA = (
    ("c1", "The deliverable is a working link to the logo file."),
    ("c2", "The logo is supplied in vector format (SVG or AI)."),
)
DELIVERABLE = DeliverableContext(type="url", content_ref="https://files.test/logo.svg")


# --- a stub standing in for google.genai's async client ---------------------


@dataclass
class _Response:
    text: str


@dataclass
class _AioModels:
    outcomes: list[Any]
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def generate_content(self, **kwargs) -> Any:
        self.calls.append(kwargs)
        outcome = self.outcomes[min(len(self.calls) - 1, len(self.outcomes) - 1)]
        if isinstance(outcome, Exception):
            raise outcome
        return _Response(text=outcome if isinstance(outcome, str) else json.dumps(outcome))


@dataclass
class _Aio:
    models: _AioModels


class StubGeminiClient:
    def __init__(self, outcomes: list[Any]) -> None:
        self.aio = _Aio(models=_AioModels(outcomes=outcomes))


def gateway_for(outcomes: list[Any]) -> tuple[GeminiAIGateway, StubGeminiClient]:
    settings = Settings(
        ai_provider="gemini",
        gemini_api_key="test-gemini-key",
        database_url="sqlite+aiosqlite:///:memory:",
    )
    client = StubGeminiClient(outcomes)
    return GeminiAIGateway(settings, client=client), client


def verification_payload(**overrides) -> dict[str, Any]:
    payload = {
        "per_criterion": [
            {"criterion_id": "c1", "pass": True, "note": "the link resolves"},
            {"criterion_id": "c2", "pass": True, "note": "the file is an SVG"},
        ],
        "verdict": "pass",
        "confidence": 0.93,
        "reasoning": "Both criteria are met.",
    }
    payload.update(overrides)
    return payload


def test_the_gemini_gateway_satisfies_the_protocol():
    gateway, _ = gateway_for([])
    assert isinstance(gateway, AIGateway)


class TestCriteria:
    async def test_criteria_are_drafted(self):
        gateway, _ = gateway_for([{"criteria": [{"text": "A vector logo is delivered."}]}])
        criteria = await gateway.draft_criteria(deal=DEAL)
        assert [c.text for c in criteria] == ["A vector logo is delivered."]

    async def test_the_schema_is_included_in_the_prompt(self):
        gateway, client = gateway_for([{"criteria": [{"text": "x"}]}])
        await gateway.draft_criteria(deal=DEAL)
        contents = client.aio.models.calls[0]["contents"]
        # The prompt carries the JSON schema so the model knows the shape.
        sent = contents[0].parts[0].text
        assert "JSON object" in sent
        assert "criteria" in sent

    async def test_json_mode_is_requested(self):
        gateway, client = gateway_for([{"criteria": [{"text": "x"}]}])
        await gateway.draft_criteria(deal=DEAL)
        config = client.aio.models.calls[0]["config"]
        assert config.response_mime_type == "application/json"

    async def test_only_the_data_needed_is_sent(self):
        gateway, client = gateway_for([{"criteria": [{"text": "x"}]}])
        await gateway.draft_criteria(deal=DEAL)
        sent = client.aio.models.calls[0]["contents"][0].parts[0].text
        assert "@" not in sent  # no emails or account refs


class TestVerification:
    async def test_a_clean_pass_is_parsed(self):
        gateway, _ = gateway_for([verification_payload()])
        judgment = await gateway.verify_deliverable(
            deal=DEAL, criteria=CRITERIA, deliverable=DELIVERABLE
        )
        assert judgment.verdict is Verdict.PASS
        assert judgment.confidence == Decimal("0.930")
        assert judgment.failed_criteria_count == 0

    async def test_a_fail_is_parsed(self):
        payload = verification_payload(
            per_criterion=[
                {"criterion_id": "c1", "pass": True, "note": "ok"},
                {"criterion_id": "c2", "pass": False, "note": "not vector"},
            ],
            verdict="fail",
        )
        gateway, _ = gateway_for([payload])
        judgment = await gateway.verify_deliverable(
            deal=DEAL, criteria=CRITERIA, deliverable=DELIVERABLE
        )
        assert judgment.verdict is Verdict.FAIL
        assert judgment.failed_criteria_count == 1

    async def test_a_pass_contradicted_by_a_failed_criterion_is_downgraded(self):
        """The shared guardrail applies to Gemini too."""
        payload = verification_payload(
            per_criterion=[
                {"criterion_id": "c1", "pass": True, "note": "ok"},
                {"criterion_id": "c2", "pass": False, "note": "no"},
            ],
            verdict="pass",
        )
        gateway, _ = gateway_for([payload])
        judgment = await gateway.verify_deliverable(
            deal=DEAL, criteria=CRITERIA, deliverable=DELIVERABLE
        )
        assert judgment.verdict is Verdict.FAIL

    async def test_json_wrapped_in_a_code_fence_is_recovered(self):
        fenced = "```json\n" + json.dumps(verification_payload()) + "\n```"
        gateway, _ = gateway_for([fenced])
        judgment = await gateway.verify_deliverable(
            deal=DEAL, criteria=CRITERIA, deliverable=DELIVERABLE
        )
        assert judgment.verdict is Verdict.PASS

    async def test_unparseable_output_is_inconclusive(self):
        gateway, _ = gateway_for(["I think it looks fine, no JSON here"])
        judgment = await gateway.verify_deliverable(
            deal=DEAL, criteria=CRITERIA, deliverable=DELIVERABLE
        )
        assert judgment.verdict is Verdict.INCONCLUSIVE

    async def test_a_retrieved_image_is_attached_as_an_inline_part(self):
        gateway, client = gateway_for([verification_payload()])
        await gateway.verify_deliverable(
            deal=DEAL,
            criteria=CRITERIA,
            deliverable=DeliverableContext(
                type="url",
                content_ref="https://files.test/logo.png",
                inspected=FetchedContent(
                    kind="image", image_base64="aGVsbG8=", media_type="image/png"
                ),
            ),
        )
        parts = client.aio.models.calls[0]["contents"][0].parts
        # Text prompt plus the image part.
        assert len(parts) == 2

    async def test_unavailable_content_is_reported_to_the_model(self):
        gateway, client = gateway_for([verification_payload()])
        await gateway.verify_deliverable(
            deal=DEAL,
            criteria=CRITERIA,
            deliverable=DeliverableContext(
                type="url",
                content_ref="https://files.test/gone",
                inspected=FetchedContent.unavailable("the link's host could not be resolved"),
            ),
        )
        sent = client.aio.models.calls[0]["contents"][0].parts[0].text
        assert "could not be retrieved" in sent

    async def test_verification_never_raises(self):
        gateway, _ = gateway_for([RuntimeError("boom")])
        judgment = await gateway.verify_deliverable(
            deal=DEAL, criteria=CRITERIA, deliverable=DELIVERABLE
        )
        assert judgment.verdict is Verdict.INCONCLUSIVE


class TestMediation:
    async def test_a_release_recommendation_is_parsed(self):
        gateway, _ = gateway_for(
            [{"recommendation": "release", "reasoning": "The work substantially meets it."}]
        )
        recommendation = await gateway.mediate_dispute(
            deal=DEAL, criteria=CRITERIA, deliverable=DELIVERABLE, verification=None
        )
        assert recommendation.recommendation is SettlementAction.RELEASE

    async def test_a_split_amount_is_validated(self):
        gateway, _ = gateway_for(
            [
                {
                    "recommendation": "split",
                    "reasoning": "Half landed.",
                    "suggested_seller_amount": 125,
                }
            ]
        )
        recommendation = await gateway.mediate_dispute(
            deal=DEAL, criteria=CRITERIA, deliverable=DELIVERABLE, verification=None
        )
        assert recommendation.recommendation is SettlementAction.SPLIT
        assert recommendation.suggested_seller_amount == Decimal("125.00")

    async def test_mediation_failure_defaults_to_refund(self):
        gateway, _ = gateway_for([RuntimeError("down"), RuntimeError("still down")])
        recommendation = await gateway.mediate_dispute(
            deal=DEAL, criteria=CRITERIA, deliverable=DELIVERABLE, verification=None
        )
        assert recommendation.recommendation is SettlementAction.REFUND


class TestConfiguration:
    def test_a_missing_key_is_reported(self):
        from app.domain.errors import AIError

        settings = Settings(
            ai_provider="gemini", gemini_api_key="", database_url="sqlite+aiosqlite:///:memory:"
        )
        gateway = GeminiAIGateway(settings, client=StubGeminiClient([]))

        async def run() -> None:
            await gateway.draft_criteria(deal=DEAL)

        import asyncio

        with pytest.raises(AIError, match="GEMINI_API_KEY"):
            asyncio.run(run())

    def test_the_provider_resolves_the_gemini_model(self):
        settings = Settings(
            ai_provider="gemini", database_url="sqlite+aiosqlite:///:memory:"
        )
        assert settings.ai_model == "gemini-3.8-flash"
        assert settings.provider_configured is False  # no key yet

    def test_an_override_wins(self):
        settings = Settings(
            ai_provider="gemini",
            ai_model_override="gemini-2.5-pro",
            database_url="sqlite+aiosqlite:///:memory:",
        )
        assert settings.ai_model == "gemini-2.5-pro"
