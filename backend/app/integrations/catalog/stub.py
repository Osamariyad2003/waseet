"""Keyless stub catalog.

Stands in for Channel3 when no API key is set, so Shop & Escrow can be
demonstrated without credentials — exactly like the AI stub.
"""

from __future__ import annotations

from decimal import Decimal

from app.integrations.catalog.interface import (
    CatalogProduct,
    PriceHistory,
    PricePoint,
    ProductDetail,
    ProductImage,
    ProductOffer,
)

_CATALOG: tuple[CatalogProduct, ...] = (
    CatalogProduct(
        id="stub_tote",
        title="Classic Canvas Tote",
        brand="Everyday Goods",
        description="A durable everyday tote with an interior pocket.",
        image_url="https://picsum.photos/seed/tote/400",
        price=Decimal("39.00"),
        currency="USD",
        available=True,
        buy_url="https://example.com/products/classic-canvas-tote",
    ),
    CatalogProduct(
        id="stub_sweater",
        title="Merino Wool Sweater",
        brand="Highland Knits",
        description="A mid-weight merino crewneck, true to size.",
        image_url="https://picsum.photos/seed/sweater/400",
        price=Decimal("120.00"),
        currency="USD",
        available=True,
        buy_url="https://example.com/products/merino-wool-sweater",
    ),
    CatalogProduct(
        id="stub_headphones",
        title="Wireless Over-Ear Headphones",
        brand="Aural",
        description="Active noise cancelling, 30-hour battery.",
        image_url="https://picsum.photos/seed/headphones/400",
        price=Decimal("199.00"),
        currency="USD",
        available=True,
        buy_url="https://example.com/products/wireless-headphones",
    ),
    CatalogProduct(
        id="stub_desk_lamp",
        title="Adjustable Desk Lamp",
        brand="Lumen",
        description="Warm-to-cool dimmable LED with a USB-C port.",
        image_url="https://picsum.photos/seed/lamp/400",
        price=Decimal("54.00"),
        currency="USD",
        available=True,
        buy_url="https://example.com/products/adjustable-desk-lamp",
    ),
    CatalogProduct(
        id="stub_sneakers",
        title="Everyday Running Sneakers",
        brand="Stride",
        description="Lightweight trainers for daily miles.",
        image_url="https://picsum.photos/seed/sneakers/400",
        price=Decimal("88.00"),
        currency="USD",
        available=True,
        buy_url="https://example.com/products/everyday-running-sneakers",
    ),
    CatalogProduct(
        id="stub_backpack",
        title="Commuter Backpack",
        brand="Transit",
        description="A 20L water-resistant pack with a padded laptop sleeve.",
        image_url="https://picsum.photos/seed/backpack/400",
        price=Decimal("72.00"),
        currency="USD",
        available=True,
        buy_url="https://example.com/products/commuter-backpack",
    ),
)


class StubCatalogGateway:
    """A fixed catalog, filtered by substring, for the keyless demo."""

    async def search(self, *, query: str, limit: int = 12) -> tuple[CatalogProduct, ...]:
        q = (query or "").strip().lower()
        if not q:
            return ()
        hits = tuple(
            p
            for p in _CATALOG
            if q in p.title.lower()
            or (p.brand and q in p.brand.lower())
            or (p.description and q in p.description.lower())
        )
        results = hits or _CATALOG
        return results[:limit]

    async def get_product(self, *, product_id: str) -> ProductDetail | None:
        match = next((p for p in _CATALOG if p.id == product_id), None)
        if not match:
            return None
        return ProductDetail(
            id=match.id,
            title=match.title,
            brand=match.brand,
            description=match.description,
            images=[ProductImage(url=match.image_url or "", cleaned_url=None, alt_text=match.title)] if match.image_url else [],
            offers=[ProductOffer(
                domain="example.com",
                price=match.price,
                compare_at_price=None,
                currency=match.currency,
                available=match.available,
                url=match.buy_url,
            )] if match.price else [],
            price=match.price,
            currency=match.currency,
            available=match.available,
            category=None,
            materials=[],
            key_features=[],
        )

    async def find_similar(self, *, product_id: str, limit: int = 12) -> tuple[CatalogProduct, ...]:
        return tuple(p for p in _CATALOG if p.id != product_id)[:limit]

    async def get_price_history(self, *, product_id: str, days: int = 90) -> PriceHistory | None:
        match = next((p for p in _CATALOG if p.id == product_id), None)
        if not match or not match.price:
            return None
        base = float(match.price)
        return PriceHistory(
            product_id=product_id,
            product_title=match.title,
            history=[
                PricePoint(price=base * 1.1, currency=match.currency, timestamp="2026-08-01T00:00:00Z"),
                PricePoint(price=base * 1.05, currency=match.currency, timestamp="2026-09-01T00:00:00Z"),
                PricePoint(price=base, currency=match.currency, timestamp="2026-10-01T00:00:00Z"),
            ],
            current_price=base,
            min_price=base,
            max_price=base * 1.1,
            mean_price=base * 1.05,
            current_status="low",
        )
