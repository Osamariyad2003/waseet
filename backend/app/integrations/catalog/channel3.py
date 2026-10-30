"""Channel3 product-catalog gateway — official SDK integration.

Uses the Channel3 Python SDK (v4) for product search. Each product is
flattened to a `CatalogProduct`: the best in-stock offer supplies the price,
availability and buy link. A failure is swallowed to an empty result — the
Shop page must stay usable even when the provider is down.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

import structlog
from channel3_sdk import AsyncChannel3

from app.config import Settings
from app.integrations.catalog.interface import CatalogProduct

logger = structlog.get_logger(__name__)


class Channel3CatalogGateway:
    """Live product search backed by Channel3."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._key = settings.channel3_api_key.get_secret_value().strip()

    async def search(self, *, query: str, limit: int = 12) -> tuple[CatalogProduct, ...]:
        query = (query or "").strip()
        if not query:
            return ()
        try:
            client = AsyncChannel3(api_key=self._key)
            page = await client.products.search(
                query=query,
                limit=max(1, min(limit, 30)),
            )
            items = page.items
        except Exception as exc:
            logger.warning("catalog.search_failed", error=str(exc))
            return ()

        products = tuple(p for item in items if (p := _to_product(item)) is not None)
        logger.info("catalog.searched", query=query, count=len(products), provider="channel3")
        return products


def _to_product(item: object) -> CatalogProduct | None:
    try:
        pid = item.id
        title = item.title
    except AttributeError:
        return None
    if not pid or not title:
        return None

    brand = None
    if item.brands:
        brand = item.brands[0].name if item.brands[0].name else None

    image_url = None
    if item.images:
        first = item.images[0]
        image_url = getattr(first, "cleaned_url", None) or getattr(first, "url", None)

    price, currency, available, buy_url = _best_offer(item.offers or [])

    description = getattr(item, "description", None)

    return CatalogProduct(
        id=pid,
        title=title,
        brand=brand,
        description=description,
        image_url=image_url,
        price=price,
        currency=currency,
        available=available,
        buy_url=buy_url,
    )


def _best_offer(offers: list) -> tuple[Decimal | None, str, bool, str | None]:
    """Prefer the cheapest in-stock offer; fall back to the first one."""
    if not offers:
        return None, "USD", False, None

    parsed: list[tuple[Decimal | None, str, bool, str | None]] = []
    for offer in offers:
        price_obj = getattr(offer, "price", None)
        amount = _as_decimal(price_obj.price) if price_obj else None
        currency = (price_obj.currency if price_obj else None) or "USD"
        availability = getattr(offer, "availability", "") or ""
        available = str(availability).lower() == "instock"
        url = getattr(offer, "url", None)
        parsed.append((amount, currency, available, url))

    if not parsed:
        return None, "USD", False, None

    in_stock = [o for o in parsed if o[2] and o[0] is not None]
    pool = in_stock or parsed
    return min(pool, key=lambda o: o[0] if o[0] is not None else Decimal("Infinity"))


def _as_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None
