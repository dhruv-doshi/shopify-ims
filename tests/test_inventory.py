import pytest
from decimal import Decimal

from src.domain.inventory import sync_unsent_products
from src.infrastructure.models import ProductDraft


@pytest.mark.asyncio
async def test_sync_unsent_products(session, monkeypatch):
    product = ProductDraft(
        batch_id=1,
        original_path="x.jpg",
        name="Pending item",
        price=Decimal("10.00"),
        discount_percent=0,
        quantity=1,
        price_options_json=[10],
        discount_options_json=[0],
        quantity_options_json=[1],
        decision="approved",
        shopify_status="unsent",
    )
    session.add(product)
    await session.commit()

    async def fake_sync(s, p):
        p.shopify_status = "ok"
        p.shopify_product_id = "gid://shopify/Product/99"
        return {"status": "ok", "product_id": "gid://shopify/Product/99", "error": None}

    monkeypatch.setattr("src.domain.inventory.sync_product_to_shopify", fake_sync)
    result = await sync_unsent_products(session)
    assert result["total"] == 1
    assert result["ok"] == 1
