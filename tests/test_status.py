from unittest.mock import AsyncMock

import pytest

from src.bot.notifications import format_finish_summary
from src.domain.status import collect_status, format_status


def test_finish_summary_says_link_closed():
    text = format_finish_summary({"approved": 1, "rejected": 0, "shopify_ok": 1})
    assert "Review link is now closed." in text


@pytest.mark.asyncio
async def test_status_without_shopify(session):
    data = await collect_status(session)
    assert data["shopify_configured"] is False
    assert data["unsent_drafts"] == 0
    text = format_status(data)
    assert "not configured" in text
    assert "Last batch: none" in text


@pytest.mark.asyncio
async def test_status_with_shopify(monkeypatch, session):
    monkeypatch.setenv("SHOPIFY_STORE_DOMAIN", "dev-store.myshopify.com")
    monkeypatch.setenv("SHOPIFY_CLIENT_ID", "client-id")
    monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", "secret")
    from src.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr(
        "src.domain.status.list_inventory_products",
        AsyncMock(return_value=[{"name": "A"}, {"name": "B"}]),
    )
    data = await collect_status(session)
    assert data["shopify_ok"] is True
    assert data["product_count"] == 2
    assert "OK" in format_status(data)
    assert "2 products" in format_status(data)
