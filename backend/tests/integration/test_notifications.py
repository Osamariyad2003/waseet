"""Lifecycle email notifications.

The email gateway is a spy (conftest's `email_spy`), and notifications are
dispatched as FastAPI background tasks that run after the response — so these
assert the real routing: funding emails the seller, delivery emails the buyer,
and a release emails both. Email is best-effort, so the spy never affects the
action itself.
"""

from __future__ import annotations

import pytest

from tests.conftest import auth
from tests.integration.test_funding_flow import confirm_both, create_deal, fund
from tests.integration.test_verification_flow import deliver

pytestmark = pytest.mark.asyncio

BUYER = "buyer@sandbox.example.com"
SELLER = "seller@sandbox.example.com"


async def test_funding_emails_the_seller(client, tokens, deal_payload, email_spy):
    deal = await create_deal(client, tokens, deal_payload)
    await confirm_both(client, tokens, deal["id"])
    await fund(client, tokens, deal["id"])

    assert email_spy.to_someone(SELLER)
    assert any("funded" in subject for subject in email_spy.subjects())


async def test_delivery_emails_the_buyer(client, tokens, deal_payload, email_spy):
    deal = await create_deal(client, tokens, deal_payload)
    await confirm_both(client, tokens, deal["id"])
    await fund(client, tokens, deal["id"])
    email_spy.sent.clear()

    await deliver(client, tokens, deal["id"], type="text", content_ref="Delivered the work.")
    assert email_spy.to_someone(BUYER)


async def test_a_confident_release_emails_both_parties(client, tokens, deal_payload, email_spy):
    deal = await create_deal(client, tokens, deal_payload)
    await confirm_both(client, tokens, deal["id"])
    await fund(client, tokens, deal["id"])
    await deliver(client, tokens, deal["id"], type="text", content_ref="A clean deliverable.")
    email_spy.sent.clear()

    result = await client.post(f"/deals/{deal['id']}/verify", headers=auth(tokens["seller"]))
    assert result.json()["released"] is True

    # Both parties hear that funds were released.
    assert email_spy.to_someone(BUYER)
    assert email_spy.to_someone(SELLER)
    assert any("released" in subject for subject in email_spy.subjects())
