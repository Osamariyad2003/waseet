"""The product catalog gateway contract.

A thin read-only port: given a search query, return normalized products a
buyer can start an escrow deal from. The concrete gateway (Channel3) and the
stub both satisfy this, so the rest of the app never depends on the provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class CatalogProduct:
    """One product, flattened to what the Shop UI and a new deal need.

    Price and availability come from the best in-stock offer; `buy_url` is that
    offer's link so the buyer can see the original listing. The money still
    only ever moves through PayPal escrow — this is reference data, not a
    checkout.
    """

    id: str
    title: str
    brand: str | None
    description: str | None
    image_url: str | None
    price: Decimal | None
    currency: str
    available: bool
    buy_url: str | None


@runtime_checkable
class CatalogGateway(Protocol):
    """Read-only product search. Never moves money."""

    async def search(self, *, query: str, limit: int = 12) -> tuple[CatalogProduct, ...]:
        """Return products matching the query, best-ranked first.

        Never raises for an unavailable provider: an outage or a bad response
        comes back as an empty tuple so the Shop page degrades to "no results"
        rather than erroring.
        """
        ...
