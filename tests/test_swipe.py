import base64
from pathlib import Path

import pytest

# 1x1 PNG
MINIMAL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

from src.domain.batches import PhotoInput, create_batch, process_batch
from src.domain.links import create_link
from src.domain.review import finish_review, record_swipe
from src.infrastructure.models import Batch, ProductDraft


async def fake_vision(_bytes, mime="image/jpeg"):
    return {
        "name": "Test Mug",
        "price_options": [9.99, 14.99],
        "discount_options": [0, 10],
        "quantity_options": [1, 5],
    }


async def fake_image(_bytes, output_path: Path, mime="image/jpeg"):
    from src.core.image_io import write_image

    return write_image(output_path, MINIMAL_PNG)


@pytest.mark.asyncio
async def test_batch_pipeline_creates_review_link(session, upload_dir):
    batch = await create_batch(session, user_id=1, chat_id=2)
    await session.commit()
    photos = [PhotoInput(bytes=MINIMAL_PNG, mime="image/png", filename="a.png")]
    token = await process_batch(
        session,
        batch.id,
        photos,
        vision_fn=fake_vision,
        image_fn=fake_image,
    )
    assert token
    from src.domain.links import get_valid_link

    link = await get_valid_link(session, token, kind="review")
    assert link is not None
    assert (upload_dir / str(batch.id) / "original_0.png").exists()


@pytest.mark.asyncio
async def test_swipe_persists_and_sets_decision(session, client, upload_dir):
    link = await create_link(session, kind="review", telegram_chat_id=1)
    batch = Batch(telegram_user_id=1, telegram_chat_id=1, status="ready", review_link_id=link.id)
    session.add(batch)
    await session.flush()
    orig = upload_dir / str(batch.id) / "original_0.png"
    gen = upload_dir / str(batch.id) / "generated_0.png"
    orig.parent.mkdir(parents=True, exist_ok=True)
    orig.write_bytes(MINIMAL_PNG)
    gen.write_bytes(MINIMAL_PNG)
    product = ProductDraft(
        batch_id=batch.id,
        original_path=str(orig),
        generated_path=str(gen),
        name="Item",
        price=__import__("decimal").Decimal("10.00"),
        discount_percent=0,
        quantity=1,
        price_options_json=[10],
        discount_options_json=[0],
        quantity_options_json=[1],
    )
    session.add(product)
    await session.commit()

    res = await client.post(
        f"/api/review/{link.token}/products/{product.id}/swipe",
        json={"direction": "right", "dx": 80, "dy": 0},
    )
    assert res.status_code == 200
    assert res.json()["decision"] == "approved"

    res = await client.post(
        f"/api/review/{link.token}/products/{product.id}/swipe",
        json={"direction": "left", "dx": -80, "dy": 0},
    )
    assert res.json()["decision"] == "rejected"


@pytest.mark.asyncio
async def test_finish_without_shopify_skips(session):
    from decimal import Decimal

    link = await create_link(session, kind="review", telegram_chat_id=1)
    batch = Batch(telegram_user_id=1, telegram_chat_id=1, status="ready", review_link_id=link.id)
    session.add(batch)
    await session.flush()
    product = ProductDraft(
        batch_id=batch.id,
        original_path="x.jpg",
        name="Approved item",
        price=Decimal("12.00"),
        discount_percent=0,
        quantity=2,
        price_options_json=[12],
        discount_options_json=[0],
        quantity_options_json=[2],
        decision="approved",
    )
    session.add(product)
    await session.commit()

    result = await finish_review(session, link.token)
    assert result["approved"] == 1
    assert result["shopify_skipped"] == 1
