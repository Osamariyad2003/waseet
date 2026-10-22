"""Set up curated demo data for the walkthrough video.

Resets every deal, then builds two that tell both halves of the story end to
end, driven entirely through the API with the stub AI and the webhook
simulator — no model key and no PayPal buyer login required:

  * "Coffee shop logo" -> RELEASED (a clean SVG passes and auto-releases)
  * "Mobile app icon"  -> DISPUTED (a raster PNG misses the vector criterion)

Run with the stack up:  uv run python scripts/demo_setup.py
"""

from __future__ import annotations

import asyncio
import sys

import httpx

API = "http://localhost:8000"
PASSWORD = "demo-password-123"
BUYER = "buyer@waseet.example.com"
SELLER = "seller@waseet.example.com"


async def login(client: httpx.AsyncClient, email: str) -> str:
    r = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    r.raise_for_status()
    return r.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def confirm_and_fund(
    client: httpx.AsyncClient, deal_id: str, buyer: str, seller: str, capture_id: str
) -> None:
    for token in (buyer, seller):
        await client.post(f"/deals/{deal_id}/criteria/confirm", headers=auth(token))
    await client.post(f"/deals/{deal_id}/order", headers=auth(buyer))
    # Fund via the simulator, so no PayPal buyer approval is needed on camera.
    await client.post(
        "/webhooks/paypal/simulate",
        json={
            "id": f"WH-DEMO-{capture_id}",
            "event_type": "PAYMENT.CAPTURE.COMPLETED",
            "resource": {
                "id": capture_id,
                "custom_id": deal_id,
                "amount": {"currency_code": "USD", "value": "250.00"},
            },
        },
    )


async def main() -> int:
    async with httpx.AsyncClient(base_url=API, timeout=30) as client:
        try:
            buyer = await login(client, BUYER)
            seller = await login(client, SELLER)
        except httpx.HTTPError as exc:
            print(f"could not reach the API at {API}: {exc}")
            return 1

        # Reset every deal (accounts are kept).
        from sqlalchemy import text

        from app.database import dispose_engine, get_session_factory

        async with get_session_factory()() as session:
            await session.execute(
                text(
                    "TRUNCATE deals, acceptance_criteria, deliverables, "
                    "verification_reports, audit_log, webhook_events "
                    "RESTART IDENTITY CASCADE"
                )
            )
            await session.commit()
        await dispose_engine()
        print("cleared existing deals")

        # --- Deal 1: the happy path -> RELEASED ---------------------------
        r = await client.post(
            "/deals",
            headers=auth(buyer),
            json={
                "seller_email": SELLER,
                "title": "Coffee shop logo",
                "description": (
                    "Design a logo for a speciality coffee shop, delivered as an SVG "
                    "vector file with a transparent background."
                ),
                "amount": "250.00",
                "currency": "USD",
            },
        )
        r.raise_for_status()
        deal1 = r.json()["id"]
        await confirm_and_fund(client, deal1, buyer, seller, "CAPTURE-DEMO-A1")
        await client.post(
            f"/deals/{deal1}/deliverable",
            headers=auth(seller),
            json={
                "type": "text",
                "content_ref": (
                    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
                    '<circle cx="32" cy="32" r="26" fill="none" stroke="#334d8f" '
                    'stroke-width="4"/><path d="M22 40h20" stroke="#334d8f" '
                    'stroke-width="4"/></svg>'
                ),
                "note": "Final logo as a scalable vector, transparent background.",
            },
        )
        v = await client.post(f"/deals/{deal1}/verify", headers=auth(seller))
        print(f"deal 1 'Coffee shop logo' -> {v.json()['state']}")

        # --- Deal 2: the dispute path -> DISPUTED -------------------------
        r = await client.post(
            "/deals",
            headers=auth(buyer),
            json={
                "seller_email": SELLER,
                "title": "Mobile app icon",
                "description": (
                    "Design an app icon delivered as an SVG vector file with a "
                    "transparent background, ready for the app stores."
                ),
                "amount": "180.00",
                "currency": "USD",
            },
        )
        r.raise_for_status()
        deal2 = r.json()["id"]
        await confirm_and_fund(client, deal2, buyer, seller, "CAPTURE-DEMO-B2")
        await client.post(
            f"/deals/{deal2}/deliverable",
            headers=auth(seller),
            # A raster PNG where the checklist asked for vector -> fails.
            json={"type": "text", "content_ref": "Final icon exported as icon.png (raster)."},
        )
        v = await client.post(f"/deals/{deal2}/verify", headers=auth(seller))
        print(f"deal 2 'Mobile app icon'  -> {v.json()['state']}")

        print("\ndemo data ready:")
        print(f"  released deal: {deal1}")
        print(f"  disputed deal: {deal2}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
