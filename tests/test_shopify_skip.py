from decimal import Decimal

import pytest

from src.infrastructure.models import ProductDraft
from src.infrastructure.shopify import create_product
from src.infrastructure.shopify_auth import clear_token_cache, get_access_token


@pytest.mark.asyncio
async def test_shopify_skipped_without_credentials():
    draft = ProductDraft(
        batch_id=1,
        original_path="x.jpg",
        name="Test",
        price=Decimal("10.00"),
        discount_percent=10,
        quantity=1,
        price_options_json=[10],
        discount_options_json=[10],
        quantity_options_json=[1],
    )
    result = await create_product(draft)
    assert result["status"] == "skipped"


@pytest.mark.asyncio
async def test_client_credentials_token_exchange(monkeypatch):
    clear_token_cache()

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"access_token": "test-token", "expires_in": 3600}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **kwargs):
            assert "oauth/access_token" in url
            assert kwargs["data"]["grant_type"] == "client_credentials"
            return FakeResponse()

    import httpx

    monkeypatch.setenv("SHOPIFY_STORE_DOMAIN", "dev-store.myshopify.com")
    monkeypatch.setenv("SHOPIFY_CLIENT_ID", "client-id")
    monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", "shpss_secret")
    monkeypatch.setenv("SHOPIFY_ADMIN_ACCESS_TOKEN", "")
    from src.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: FakeClient())

    token = await get_access_token()
    assert token == "test-token"
    clear_token_cache()


@pytest.mark.asyncio
async def test_shopify_success_mocked(monkeypatch):
    draft = ProductDraft(
        batch_id=1,
        original_path="x.jpg",
        name="Test",
        price=Decimal("10.00"),
        discount_percent=0,
        quantity=1,
        price_options_json=[10],
        discount_options_json=[0],
        quantity_options_json=[1],
    )

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": {
                    "productCreate": {
                        "product": {
                            "id": "gid://shopify/Product/1",
                            "title": "Test",
                            "variants": {
                                "nodes": [
                                    {
                                        "id": "gid://shopify/ProductVariant/1",
                                        "inventoryItem": {"id": "gid://shopify/InventoryItem/1"},
                                    }
                                ]
                            },
                        },
                        "userErrors": [],
                    },
                    "productVariantsBulkUpdate": {
                        "productVariants": [{"id": "gid://shopify/ProductVariant/1", "price": "10.00"}],
                        "userErrors": [],
                    },
                    "inventorySetQuantities": {"userErrors": []},
                    "locations": {"edges": [{"node": {"id": "gid://shopify/Location/1"}}]},
                }
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return FakeResponse()

    import httpx

    monkeypatch.setenv("SHOPIFY_STORE_DOMAIN", "dev-store.myshopify.com")
    monkeypatch.setenv("SHOPIFY_CLIENT_ID", "client-id")
    monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", "shpss_secret")
    monkeypatch.setenv("SHOPIFY_ADMIN_ACCESS_TOKEN", "")
    from src.core.config import get_settings

    get_settings.cache_clear()

    async def fake_token():
        return "test-token"

    monkeypatch.setattr("src.infrastructure.shopify.get_access_token", fake_token)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: FakeClient())

    result = await create_product(draft)
    assert result["status"] == "ok"
    assert result["product_id"] == "gid://shopify/Product/1"
