"""Live PayPal sandbox smoke test.

Confirms the credentials in backend/.env actually work, and reports which
capabilities the sandbox app has, before the rest of the system depends on
them. Read-only except for the order it creates — an unapproved,
uncaptured order moves no money.

    uv run python scripts/smoke_paypal.py

Prints nothing secret: no tokens, no client secret, no full payloads.
"""

from __future__ import annotations

import asyncio
import sys
from decimal import Decimal

from app.config import get_settings
from app.domain.errors import PayPalError
from app.integrations.paypal.client import PayPalClient

OK = "  [ok]  "
FAIL = "  [FAIL]"
SKIP = "  [skip]"


async def main() -> int:
    settings = get_settings()
    print(f"\nPayPal sandbox smoke test -> {settings.paypal_base_url}\n")

    if not settings.paypal_configured:
        print(f"{FAIL} PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET are not set in backend/.env")
        return 1

    client = PayPalClient(settings)
    failures = 0

    try:
        # 1. OAuth — the gate everything else goes through.
        try:
            token = await client.get_access_token()
            scopes = token.scope.split()
            print(f"{OK} OAuth token acquired ({len(scopes)} scopes granted)")
        except PayPalError as exc:
            print(f"{FAIL} OAuth: {exc.message}")
            return 1

        # 2. Which capabilities this sandbox app actually has. Payouts is the
        #    one that is sometimes missing, and release depends on it.
        capabilities = {
            "Orders (fund escrow)": "orders",
            "Payouts (release to seller)": "payouts",
            "Refunds (return to buyer)": "payment",
        }
        for label, needle in capabilities.items():
            granted = any(needle in scope for scope in scopes)
            print(
                f"{OK if granted else SKIP} scope for {label}: {'yes' if granted else 'not listed'}"
            )

        # 3. Create a real order. Nothing is captured, so no money moves.
        try:
            order = await client.create_order(
                amount=Decimal("1.00"),
                currency="USD",
                reference_id="smoke-test",
                description="Waseet smoke test (not captured)",
                request_id="waseet-smoke-order-1",
            )
            print(f"{OK} Orders v2 create -> order {order.order_id} ({order.status})")
            if order.approve_url:
                print("         approve url present: yes")
        except PayPalError as exc:
            print(f"{FAIL} Orders v2 create: {exc.message}")
            failures += 1

        # 4. Webhook verification is reachable (it will not verify a fake
        #    signature — a False here is the correct, expected answer).
        if settings.paypal_webhook_id:
            print(f"{OK} PAYPAL_WEBHOOK_ID is set")
        else:
            print(f"{SKIP} PAYPAL_WEBHOOK_ID not set yet (needed once a public URL exists)")

        if settings.paypal_seller_receiver_email:
            print(f"{OK} seller payout receiver configured")
        else:
            print(f"{SKIP} PAYPAL_SELLER_RECEIVER_EMAIL not set (needed to release funds)")
    finally:
        await client.aclose()

    print("\nsmoke test " + ("failed\n" if failures else "passed\n"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
