"""The product catalog (Channel3): Shop & Escrow.

A buyer searches a real product catalog and starts an escrow deal pre-filled
from a product. This router is read-only and moves no money — it only returns
reference data. The escrow guardrails live in the deal lifecycle, which the
buyer enters afterwards via the normal create-deal flow.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.schemas.deals import CatalogProductResponse
from app.dependencies import CatalogDep, CurrentUserDep

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/search", response_model=list[CatalogProductResponse])
async def search_catalog(
    user: CurrentUserDep,
    catalog: CatalogDep,
    q: str = Query(min_length=1, max_length=200, description="Search text."),
    limit: int = Query(default=12, ge=1, le=40),
) -> list[CatalogProductResponse]:
    """Search products to start a deal from.

    Signed-in only, so buy-link clicks can be attributed to the user. A
    provider outage degrades to an empty list rather than an error.
    """
    products = await catalog.search(query=q, limit=limit)
    return [
        CatalogProductResponse(
            id=p.id,
            title=p.title,
            brand=p.brand,
            description=p.description,
            image_url=p.image_url,
            price=p.price,
            currency=p.currency,
            available=p.available,
            buy_url=p.buy_url,
        )
        for p in products
    ]
