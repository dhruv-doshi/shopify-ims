from datetime import datetime, timedelta, timezone

import pytest

from src.domain.links import create_link, get_valid_link


@pytest.mark.asyncio
async def test_create_and_get_valid_link(session):
    link = await create_link(session, kind="review", telegram_chat_id=123)
    await session.commit()
    found = await get_valid_link(session, link.token, kind="review")
    assert found is not None
    assert found.token == link.token


@pytest.mark.asyncio
async def test_expired_link_returns_none(session):
    link = await create_link(session, kind="review", ttl_hours=-1)
    link.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await session.commit()
    assert await get_valid_link(session, link.token, kind="review") is None


@pytest.mark.asyncio
async def test_finish_expires_link(session):
    from decimal import Decimal

    from src.domain.review import finish_review
    from src.infrastructure.models import Batch, ProductDraft

    link = await create_link(session, kind="review", telegram_chat_id=1)
    batch = Batch(telegram_user_id=1, telegram_chat_id=1, status="ready", review_link_id=link.id)
    session.add(batch)
    await session.flush()
    product = ProductDraft(
        batch_id=batch.id,
        original_path="x.jpg",
        name="Item",
        price=Decimal("10.00"),
        discount_percent=0,
        quantity=1,
        price_options_json=[10],
        discount_options_json=[0],
        quantity_options_json=[1],
        decision="rejected",
    )
    session.add(product)
    await session.commit()

    await finish_review(session, link.token)
    assert await get_valid_link(session, link.token, kind="review") is None

