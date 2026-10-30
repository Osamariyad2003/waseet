"""The product catalog gateway contract.

A thin read-only port: given a search query, return normalized products a
buyer can start an escrow deal from. The concrete gateway (Channel3) and the
stub both satisfy this, so the rest of the app never depends on the provider.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class CatalogProduct:
    """One product, flattened to what the Shop UI and a new deal need."""

    id: str
    title: str
    brand: str | None
    description: str | None
    image_url: str | None
    price: Decimal | None
    currency: str
    available: bool
    buy_url: str | None


@dataclass(frozen=True, slots=True)
class ProductOffer:
    """A single merchant offer for a product."""

    domain: str
    price: Decimal | None
    compare_at_price: Decimal | None
    currency: str
    available: bool
    url: str | None


@dataclass(frozen=True, slots=True)
class ProductImage:
    """A product image with optional cleaned (background-removed) variant."""

    url: str
    cleaned_url: str | None
    alt_text: str | None


@dataclass(frozen=True, slots=True)
class ProductDetail:
    """Full product detail with all offers, images, and metadata."""

    id: str
    title: str
    brand: str | None
    description: str | None
    images: list[ProductImage]
    offers: list[ProductOffer]
    price: Decimal | None
    currency: str
    available: bool
    category: str | None
    materials: list[str]
    key_features: list[str]


@dataclass(frozen=True, slots=True)
class PricePoint:
    """A single historical price data point."""

    price: float
    currency: str
    timestamp: str


@dataclass(frozen=True, slots=True)
class PriceHistory:
    """Price history with statistics for a product."""

    product_id: str
    product_title: str | None
    history: list[PricePoint]
    current_price: float | None
    min_price: float | None
    max_price: float | None
    mean_price: float | None
    current_status: str | None  # "low" | "typical" | "high"


@runtime_checkable
class CatalogGateway(Protocol):
    """Read-only product catalog. Never moves money."""

    async def search(self, *, query: str, limit: int = 12) -> tuple[CatalogProduct, ...]:
        ...

    async def get_product(self, *, product_id: str) -> ProductDetail | None:
        ...

    async def find_similar(self, *, product_id: str, limit: int = 12) -> tuple[CatalogProduct, ...]:
        ...

    async def get_price_history(self, *, product_id: str, days: int = 90) -> PriceHistory | None:
        ...
