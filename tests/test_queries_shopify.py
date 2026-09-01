import pytest
from unittest.mock import AsyncMock

from src.domain.queries import load_inventory_rows, handle_question


@pytest.mark.asyncio
async def test_load_inventory_uses_shopify_when_configured(monkeypatch, session):
    monkeypatch.setenv("SHOPIFY_STORE_DOMAIN", "dev-store.myshopify.com")
    monkeypatch.setenv("SHOPIFY_CLIENT_ID", "client-id")
    monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", "secret")
    from src.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr(
        "src.domain.queries.list_inventory_products",
        AsyncMock(
            return_value=[
                {
                    "id": "gid://shopify/Product/1",
                    "name": "Live product",
                    "price": 10.0,
                    "quantity": 2,
                    "decision": "active",
                    "shopify_status": "ok",
                    "source": "shopify",
                }
            ]
        ),
    )

    rows = await load_inventory_rows(session)
    assert len(rows) == 1
    assert rows[0]["source"] == "shopify"


@pytest.mark.asyncio
async def test_handle_question_empty_shopify_store(monkeypatch, session):
    monkeypatch.setenv("SHOPIFY_STORE_DOMAIN", "dev-store.myshopify.com")
    monkeypatch.setenv("SHOPIFY_CLIENT_ID", "client-id")
    monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", "secret")
    from src.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr("src.domain.queries.list_inventory_products", AsyncMock(return_value=[]))

    result = await handle_question(session, "how many products?", 1)
    assert result["mode"] == "text"
    assert "no products" in result["text"].lower()
