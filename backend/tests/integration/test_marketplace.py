"""The marketplace: seller offers that a buyer browses.

Offers are listings only — they hold no money and drive no state — so these
assert the access rules (only a seller posts; delist hides) and that an offer
surfaces in the public list a buyer sees.
"""

from __future__ import annotations

import pytest

from tests.conftest import auth

pytestmark = pytest.mark.asyncio

OFFER = {
    "title": "Logo & brand mark",
    "description": "A custom vector logo with two revisions.",
    "category": "design",
    "amount": "250.00",
    "currency": "USD",
}


async def post_offer(client, tokens, **overrides):
    return await client.post(
        "/offers", json={**OFFER, **overrides}, headers=auth(tokens["seller"])
    )


async def test_a_seller_posts_an_offer_and_a_buyer_sees_it(client, tokens):
    created = await post_offer(client, tokens)
    assert created.status_code == 201, created.text
    assert created.json()["seller"]["role"] == "seller"

    listed = await client.get("/offers", headers=auth(tokens["buyer"]))
    assert listed.status_code == 200
    titles = [o["title"] for o in listed.json()]
    assert "Logo & brand mark" in titles


async def test_a_buyer_cannot_post_an_offer(client, tokens):
    response = await client.post("/offers", json=OFFER, headers=auth(tokens["buyer"]))
    assert response.status_code == 422
    assert "seller" in response.text


async def test_my_offers_lists_only_the_sellers_own(client, tokens):
    await post_offer(client, tokens)
    mine = await client.get("/offers/mine", headers=auth(tokens["seller"]))
    assert mine.status_code == 200
    assert len(mine.json()) == 1


async def test_delisting_hides_an_offer_from_the_marketplace(client, tokens):
    offer_id = (await post_offer(client, tokens)).json()["id"]

    delisted = await client.delete(f"/offers/{offer_id}", headers=auth(tokens["seller"]))
    assert delisted.status_code == 204

    listed = await client.get("/offers", headers=auth(tokens["buyer"]))
    assert all(o["id"] != offer_id for o in listed.json())

    # But it still shows in the seller's own list, marked inactive.
    mine = await client.get("/offers/mine", headers=auth(tokens["seller"]))
    assert mine.json()[0]["active"] is False


async def test_a_seller_cannot_delist_another_sellers_offer(client, tokens, users, session):
    """A delist on an offer that isn't yours is refused as not found."""
    import uuid

    from app.models.offer import Offer

    other = Offer(
        id=uuid.uuid4(),
        seller_id=users["buyer"].id,  # some other user's offer
        title="x",
        description="",
        category="other",
        amount="10.00",
        currency="USD",
        active=True,
    )
    session.add(other)
    await session.commit()

    response = await client.delete(f"/offers/{other.id}", headers=auth(tokens["seller"]))
    assert response.status_code == 422
