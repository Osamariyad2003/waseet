"""The product catalog (Channel3): Shop & Escrow.

A buyer searches a real product catalog and starts an escrow deal pre-filled
from a product. This router is read-only and moves no money — it only returns
reference data.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, Query

from app.api.schemas.deals import (
    CatalogProductResponse,
    PriceHistoryResponse,
    PricePointResponse,
    ProductDetailResponse,
    ProductImageResponse,
    ProductOfferResponse,
)
from app.dependencies import CatalogDep, CurrentUserDep

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/search", response_model=list[CatalogProductResponse])
async def search_catalog(
    user: CurrentUserDep,
    catalog: CatalogDep,
    q: str = Query(min_length=1, max_length=200, description="Search text."),
    limit: int = Query(default=12, ge=1, le=40),
) -> list[CatalogProductResponse]:
    """Search products to start a deal from."""
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


@router.get("/products/{product_id}", response_model=ProductDetailResponse)
async def get_product(
    user: CurrentUserDep,
    catalog: CatalogDep,
    product_id: str = Path(min_length=1, max_length=100),
) -> ProductDetailResponse:
    """Get full product details including all offers and images."""
    detail = await catalog.get_product(product_id=product_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Product not found.")
    return ProductDetailResponse(
        id=detail.id,
        title=detail.title,
        brand=detail.brand,
        description=detail.description,
        images=[ProductImageResponse(url=img.url, cleaned_url=img.cleaned_url, alt_text=img.alt_text) for img in detail.images],
        offers=[ProductOfferResponse(
            domain=o.domain,
            price=o.price,
            compare_at_price=o.compare_at_price,
            currency=o.currency,
            available=o.available,
            url=o.url,
        ) for o in detail.offers],
        price=detail.price,
        currency=detail.currency,
        available=detail.available,
        category=detail.category,
        materials=detail.materials,
        key_features=detail.key_features,
    )


@router.get("/products/{product_id}/similar", response_model=list[CatalogProductResponse])
async def get_similar_products(
    user: CurrentUserDep,
    catalog: CatalogDep,
    product_id: str = Path(min_length=1, max_length=100),
    limit: int = Query(default=6, ge=1, le=20),
) -> list[CatalogProductResponse]:
    """Find products similar to a given product."""
    products = await catalog.find_similar(product_id=product_id, limit=limit)
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


@router.get("/products/{product_id}/price-history", response_model=PriceHistoryResponse)
async def get_price_history(
    user: CurrentUserDep,
    catalog: CatalogDep,
    product_id: str = Path(min_length=1, max_length=100),
    days: int = Query(default=90, ge=1, le=90),
) -> PriceHistoryResponse:
    """Get price history and statistics for a product."""
    history = await catalog.get_price_history(product_id=product_id, days=days)
    if history is None:
        raise HTTPException(status_code=404, detail="Price history not available.")
    return PriceHistoryResponse(
        product_id=history.product_id,
        product_title=history.product_title,
        history=[PricePointResponse(price=p.price, currency=p.currency, timestamp=p.timestamp) for p in history.history],
        current_price=history.current_price,
        min_price=history.min_price,
        max_price=history.max_price,
        mean_price=history.mean_price,
        current_status=history.current_status,
    )
