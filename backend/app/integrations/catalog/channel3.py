"""Channel3 product-catalog gateway — official SDK integration.

Uses the Channel3 Python SDK (v4) for product search, detail, similar, and
price history. Each product is flattened to our domain types. A failure is
swallowed so the Shop page stays usable even when the provider is down.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

import structlog
from channel3_sdk import AsyncChannel3

from app.config import Settings
from app.integrations.catalog.interface import (
    CatalogProduct,
    PriceHistory,
    PricePoint,
    ProductDetail,
    ProductImage,
    ProductOffer,
)

logger = structlog.get_logger(__name__)


class Channel3CatalogGateway:
    """Live product catalog backed by Channel3."""

    def __init__(self, settings: Settings) -> None:
        self._key = settings.channel3_api_key.get_secret_value().strip()

    def _client(self) -> AsyncChannel3:
        return AsyncChannel3(api_key=self._key)

    # -- search ---------------------------------------------------------------

    async def search(self, *, query: str, limit: int = 12) -> tuple[CatalogProduct, ...]:
        query = (query or "").strip()
        if not query:
            return ()
        try:
            client = self._client()
            page = await client.products.search(
                query=query,
                limit=max(1, min(limit, 30)),
            )
            items = page.items
        except Exception as exc:
            logger.warning("catalog.search_failed", error=str(exc))
            return ()

        products = tuple(p for item in items if (p := _to_catalog_product(item)) is not None)
        logger.info("catalog.searched", query=query, count=len(products), provider="channel3")
        return products

    # -- product detail -------------------------------------------------------

    async def get_product(self, *, product_id: str) -> ProductDetail | None:
        try:
            client = self._client()
            item = await client.products.retrieve(product_id=product_id)
        except Exception as exc:
            logger.warning("catalog.get_product_failed", product_id=product_id, error=str(exc))
            return None
        return _to_product_detail(item)

    # -- similar products -----------------------------------------------------

    async def find_similar(self, *, product_id: str, limit: int = 12) -> tuple[CatalogProduct, ...]:
        try:
            client = self._client()
            page = await client.products.find_similar(
                product_id=product_id,
                limit=max(1, min(limit, 30)),
            )
            items = page.items
        except Exception as exc:
            logger.warning("catalog.find_similar_failed", product_id=product_id, error=str(exc))
            return ()

        products = tuple(p for item in items if (p := _to_catalog_product(item)) is not None)
        logger.info("catalog.similar", product_id=product_id, count=len(products))
        return products

    # -- price history --------------------------------------------------------

    async def get_price_history(self, *, product_id: str, days: int = 90) -> PriceHistory | None:
        try:
            client = self._client()
            history = await client.price_tracking.retrieve_history(
                canonical_product_id=product_id,
                days=min(days, 90),
            )
        except Exception as exc:
            logger.warning("catalog.price_history_failed", product_id=product_id, error=str(exc))
            return None

        points: list[PricePoint] = []
        for entry in (history.history or []):
            ts = entry.timestamp
            points.append(PricePoint(
                price=entry.price,
                currency=entry.currency,
                timestamp=str(ts) if ts else "",
            ))

        stats = history.statistics
        return PriceHistory(
            product_id=product_id,
            product_title=getattr(history, "product_title", None),
            history=points,
            current_price=stats.current_price if stats else None,
            min_price=stats.min_price if stats else None,
            max_price=stats.max_price if stats else None,
            mean_price=stats.mean if stats else None,
            current_status=stats.current_status if stats else None,
        )


# ---------------------------------------------------------------------------
# Converters
# ---------------------------------------------------------------------------

def _to_catalog_product(item: object) -> CatalogProduct | None:
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


def _to_product_detail(item: object) -> ProductDetail | None:
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

    images: list[ProductImage] = []
    for img in (item.images or []):
        images.append(ProductImage(
            url=getattr(img, "url", ""),
            cleaned_url=getattr(img, "cleaned_url", None),
            alt_text=getattr(img, "alt_text", None),
        ))

    offers: list[ProductOffer] = []
    for offer in (item.offers or []):
        price_obj = getattr(offer, "price", None)
        offers.append(ProductOffer(
            domain=getattr(offer, "domain", ""),
            price=_as_decimal(price_obj.price) if price_obj else None,
            compare_at_price=_as_decimal(getattr(price_obj, "compare_at_price", None)) if price_obj else None,
            currency=(price_obj.currency if price_obj else None) or "USD",
            available=str(getattr(offer, "availability", "") or "").lower() == "instock",
            url=getattr(offer, "url", None),
        ))

    price, currency, available, _ = _best_offer(item.offers or [])

    category_obj = getattr(item, "category", None)
    category = category_obj.title if category_obj and hasattr(category_obj, "title") else None

    return ProductDetail(
        id=pid,
        title=title,
        brand=brand,
        description=getattr(item, "description", None),
        images=images,
        offers=offers,
        price=price,
        currency=currency,
        available=available,
        category=category,
        materials=getattr(item, "materials", None) or [],
        key_features=getattr(item, "key_features", None) or [],
    )


def _best_offer(offers: list) -> tuple[Decimal | None, str, bool, str | None]:
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
