from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.domain.shopify_seed import SEED_PREFIX, seed_shopify_catalog


@pytest.mark.asyncio
async def test_seed_not_configured(session):
    result = await seed_shopify_catalog(session)
    assert result["products_created"] == 0
    assert "Shopify not configured" in result["errors"][0]


@pytest.mark.asyncio
async def test_seed_idempotent_skips_existing(monkeypatch, session):
    monkeypatch.setenv("SHOPIFY_STORE_DOMAIN", "dev-store.myshopify.com")
    monkeypatch.setenv("SHOPIFY_CLIENT_ID", "client-id")
    monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", "secret")
    from src.core.config import get_settings
    from src.domain.shopify_seed import SEED_FIXTURES

    get_settings.cache_clear()

    all_titles = [
        {"title": SEED_PREFIX + f["name"], "variant_id": "gid://shopify/ProductVariant/1"}
        for f in SEED_FIXTURES
    ]
    monkeypatch.setattr(
        "src.domain.shopify_seed.list_seed_products",
        AsyncMock(return_value=all_titles),
    )

    create_calls = {"n": 0}

    async def fake_sync(session, draft):
        create_calls["n"] += 1
        draft.shopify_status = "ok"
        draft.shopify_product_id = "gid://shopify/Product/1"
        return {"status": "ok", "product_id": "gid://shopify/Product/1", "variant_id": "gid://shopify/ProductVariant/1"}

    monkeypatch.setattr("src.domain.shopify_seed.sync_product_to_shopify", fake_sync)
    monkeypatch.setattr(
        "src.domain.shopify_seed.create_demo_orders",
        AsyncMock(return_value={"orders_created": 0, "orders_skipped": 4, "error": None}),
    )
    monkeypatch.setattr("src.domain.shopify_seed.ensure_analytics_data", AsyncMock())

    result = await seed_shopify_catalog(session)
    assert result["products_created"] == 0
    assert result["products_skipped"] >= 1
    assert create_calls["n"] == 0

    result2 = await seed_shopify_catalog(session)
    assert result2["products_created"] == 0
    assert result2["products_skipped"] >= 1


@pytest.mark.asyncio
async def test_seed_orders_failure_still_creates_products(monkeypatch, session):
    monkeypatch.setenv("SHOPIFY_STORE_DOMAIN", "dev-store.myshopify.com")
    monkeypatch.setenv("SHOPIFY_CLIENT_ID", "client-id")
    monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", "secret")
    from src.core.config import get_settings

    get_settings.cache_clear()

    monkeypatch.setattr("src.domain.shopify_seed.list_seed_products", AsyncMock(return_value=[]))

    async def fake_sync(session, draft):
        draft.shopify_status = "ok"
        draft.shopify_product_id = "gid://shopify/Product/1"
        return {"status": "ok", "product_id": "gid://shopify/Product/1", "variant_id": "gid://shopify/ProductVariant/1"}

    monkeypatch.setattr("src.domain.shopify_seed.sync_product_to_shopify", fake_sync)
    monkeypatch.setattr(
        "src.domain.shopify_seed.create_demo_orders",
        AsyncMock(return_value={"orders_created": 0, "orders_skipped": 4, "error": "Access denied"}),
    )
    monkeypatch.setattr("src.domain.shopify_seed.ensure_analytics_data", AsyncMock())

    result = await seed_shopify_catalog(session)
    assert result["products_created"] >= 1
    assert result["orders_created"] == 0
    assert any("Orders" in e for e in result["errors"])
