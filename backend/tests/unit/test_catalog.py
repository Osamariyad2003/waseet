"""The product catalog gateways: the stub, and the Channel3 response parser."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.integrations.catalog.channel3 import _best_offer, _to_product
from app.integrations.catalog.stub import StubCatalogGateway


@pytest.mark.asyncio
async def test_stub_filters_by_substring() -> None:
    gw = StubCatalogGateway()
    results = await gw.search(query="sweater")
    assert any("sweater" in p.title.lower() for p in results)


@pytest.mark.asyncio
async def test_stub_blank_query_returns_nothing() -> None:
    gw = StubCatalogGateway()
    assert await gw.search(query="   ") == ()


@pytest.mark.asyncio
async def test_stub_respects_limit() -> None:
    gw = StubCatalogGateway()
    results = await gw.search(query="a", limit=2)  # "a" matches most of the catalog
    assert len(results) <= 2


def test_parser_picks_cheapest_in_stock_offer() -> None:
    product = _to_product(
        {
            "id": "prod_1",
            "title": "Classic Canvas Tote",
            "brands": [{"id": "b", "name": "Example Brand"}],
            "images": [{"url": "u", "cleaned_url": "c"}],
            "offers": [
                {"url": "https://a.com", "price": {"price": 39.0, "currency": "USD", "availability": "InStock"}},
                {"url": "https://b.com", "price": {"price": 29.0, "currency": "USD", "availability": "InStock"}},
                {"url": "https://c.com", "price": {"price": 19.0, "currency": "USD", "availability": "OutOfStock"}},
            ],
        }
    )
    assert product is not None
    assert product.brand == "Example Brand"
    assert product.image_url == "c"  # prefers the cleaned, background-removed image
    assert product.price == Decimal("29.00")  # cheapest *in-stock*
    assert product.available is True
    assert product.buy_url == "https://b.com"


def test_parser_rejects_item_without_id_or_title() -> None:
    assert _to_product({"title": "No id"}) is None
    assert _to_product({"id": "x"}) is None
    assert _to_product("not a dict") is None


def test_best_offer_handles_no_offers() -> None:
    price, currency, available, url = _best_offer([])
    assert price is None and currency == "USD" and available is False and url is None
