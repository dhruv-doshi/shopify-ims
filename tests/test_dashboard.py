from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from src.core.llm import fallback_dashboard_spec
from src.domain.analytics_seed import build_snapshot, ensure_analytics_data
from src.domain.dashboard import create_dashboard
from src.domain.links import create_link, get_valid_link
from src.infrastructure.models import MockProduct, MockSale


@pytest.mark.asyncio
async def test_ensure_analytics_data_idempotent(session):
    await ensure_analytics_data(session)
    count1 = await session.scalar(select(func.count()).select_from(MockProduct))
    await ensure_analytics_data(session)
    count2 = await session.scalar(select(func.count()).select_from(MockProduct))
    assert count1 == count2
    assert count1 and count1 >= 8


@pytest.mark.asyncio
async def test_ensure_analytics_data_fixtures_without_drafts(session):
    await ensure_analytics_data(session)
    products = list((await session.execute(select(MockProduct))).scalars())
    sales = list((await session.execute(select(MockSale))).scalars())
    assert len(products) >= 8
    assert len(sales) >= 1


@pytest.mark.asyncio
async def test_create_dashboard_stores_prompt(monkeypatch, session):
    async def fake_spec(prompt, snapshot):
        return {
            "title": "Low stock",
            "subtitle": "Demo analytics",
            "telegram_summary": "Low stock summary",
            "kpis": [{"label": "SKUs", "value": "3", "hint": ""}],
            "charts": [],
            "tables": [],
        }

    monkeypatch.setattr("src.domain.dashboard.build_dashboard_spec", fake_spec)
    result = await create_dashboard(session, "low stock", chat_id=99)
    assert "/d/" in result["url"]
    token = result["url"].rstrip("/").split("/")[-1]
    link = await get_valid_link(session, token, kind="data")
    assert link is not None
    assert link.payload_json["prompt"] == "low stock"


@pytest.mark.asyncio
async def test_fallback_spec_has_widgets(session):
    await ensure_analytics_data(session)
    snapshot = await build_snapshot(session)
    spec = fallback_dashboard_spec("overview", snapshot)
    assert len(spec["kpis"]) >= 4
    assert spec["charts"] or spec["tables"]
    assert "Demo analytics" in spec["subtitle"]


@pytest.mark.asyncio
async def test_expired_data_api_returns_404(client, session):
    link = await create_link(
        session,
        kind="data",
        payload={"title": "x", "columns": [], "rows": []},
    )
    link.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await session.commit()
    response = await client.get(f"/api/data/{link.token}")
    assert response.status_code == 404
