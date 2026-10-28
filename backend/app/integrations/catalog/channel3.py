"""Channel3 product-catalog gateway.

Calls Channel3's search API (`POST /v1/search`, `x-api-key` auth) and flattens
each product to a `CatalogProduct`: the best in-stock offer supplies the price,
availability and buy link. A failure is swallowed to an empty result — the
Shop page must stay usable even when the provider is down.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

import httpx
import structlog

from app.config import Settings
from app.integrations.catalog.interface import CatalogProduct

logger = structlog.get_logger(__name__)

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


class Channel3CatalogGateway:
    """Live product search backed by Channel3."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._key = settings.channel3_api_key.get_secret_value().strip()
        self._base_url = settings.channel3_base_url.rstrip("/")

    async def search(self, *, query: str, limit: int = 12) -> tuple[CatalogProduct, ...]:
        query = (query or "").strip()
        if not query:
            return ()
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    f"{self._base_url}/search",
                    headers={"x-api-key": self._key, "Content-Type": "application/json"},
                    json={"query": query, "limit": max(1, min(limit, 40))},
                )
                resp.raise_for_status()
                payload = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            # Never surface a provider outage as a 500 — degrade to no results.
            logger.warning("catalog.search_failed", error=str(exc))
            return ()

        # The API may return a bare list or an object wrapping one.
        items = payload if isinstance(payload, list) else payload.get("products") or payload.get("results") or []
        products = tuple(p for item in items if (p := _to_product(item)) is not None)
        logger.info("catalog.searched", query=query, count=len(products), provider="channel3")
        return products


def _to_product(item: object) -> CatalogProduct | None:
    if not isinstance(item, dict):
        return None
    pid = str(item.get("id") or "").strip()
    title = str(item.get("title") or "").strip()
    if not pid or not title:
        return None

    brands = item.get("brands") or []
    brand = None
    if isinstance(brands, list) and brands and isinstance(brands[0], dict):
        brand = str(brands[0].get("name") or "").strip() or None

    image_url = None
    images = item.get("images") or []
    if isinstance(images, list) and images and isinstance(images[0], dict):
        first = images[0]
        image_url = (first.get("cleaned_url") or first.get("url")) or None

    price, currency, available, buy_url = _best_offer(item.get("offers") or [])

    description = item.get("description")
    description = str(description).strip() if description else None

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


def _best_offer(offers: object) -> tuple[Decimal | None, str, bool, str | None]:
    """Prefer the cheapest in-stock offer; fall back to the first one."""
    if not isinstance(offers, list):
        return None, "USD", False, None

    parsed: list[tuple[Decimal | None, str, bool, str | None]] = []
    for offer in offers:
        if not isinstance(offer, dict):
            continue
        price_obj = offer.get("price") or {}
        amount = _as_decimal(price_obj.get("price")) if isinstance(price_obj, dict) else None
        currency = str((price_obj.get("currency") if isinstance(price_obj, dict) else None) or "USD").upper()
        availability = str((price_obj.get("availability") if isinstance(price_obj, dict) else "") or "")
        available = availability.lower() == "instock"
        url = str(offer.get("url") or "").strip() or None
        parsed.append((amount, currency, available, url))

    if not parsed:
        return None, "USD", False, None

    in_stock = [o for o in parsed if o[2] and o[0] is not None]
    pool = in_stock or parsed
    # Cheapest priced offer in the pool; unpriced offers sort last.
    return min(pool, key=lambda o: o[0] if o[0] is not None else Decimal("Infinity"))


def _as_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None
