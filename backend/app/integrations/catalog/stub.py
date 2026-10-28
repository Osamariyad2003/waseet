"""Keyless stub catalog.

Stands in for Channel3 when no API key is set, so Shop & Escrow can be
demonstrated without credentials — exactly like the AI stub. It filters a
small fixed catalog by a case-insensitive substring match on the query.
"""

from __future__ import annotations

from decimal import Decimal

from app.integrations.catalog.interface import CatalogProduct

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
        # If nothing matches the query, show the whole catalog rather than an
        # empty page — the demo should always have something to click.
        results = hits or _CATALOG
        return results[:limit]
