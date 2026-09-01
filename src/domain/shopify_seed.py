from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.domain.analytics_seed import ensure_analytics_data
from src.domain.inventory import sync_product_to_shopify
from src.infrastructure.models import Batch, ProductDraft
from src.infrastructure.shopify import create_demo_orders, list_seed_products

SEED_PREFIX = "IMS Seed — "

SEED_FIXTURES = [
    {"name": "Gold Bangle Set", "price": Decimal("29.99"), "quantity": 12, "discount": 10},
    {"name": "Glass Bangles", "price": Decimal("9.99"), "quantity": 20, "discount": 0},
    {"name": "Kundan Bracelet", "price": Decimal("39.99"), "quantity": 8, "discount": 10},
    {"name": "Silver Cuff", "price": Decimal("24.99"), "quantity": 15, "discount": 0},
    {"name": "Pearl Bangle", "price": Decimal("19.99"), "quantity": 10, "discount": 10},
    {"name": "Temple Jewelry Bangle", "price": Decimal("49.99"), "quantity": 6, "discount": 0},
    {"name": "Meenakari Bangles", "price": Decimal("34.99"), "quantity": 9, "discount": 10},
    {"name": "Oxidised Cuff", "price": Decimal("14.99"), "quantity": 18, "discount": 0},
]


async def _get_or_create_seed_batch(session: AsyncSession) -> Batch:
    result = await session.execute(select(Batch).where(Batch.status == "seed").limit(1))
    batch = result.scalar_one_or_none()
    if batch:
        return batch
    batch = Batch(telegram_user_id=0, telegram_chat_id=0, status="seed")
    session.add(batch)
    await session.flush()
    return batch


def _seed_images() -> list[Path]:
    folder = Path("temp/bangle-test-images")
    if not folder.is_dir():
        return []
    return sorted(folder.glob("*.jpg"))


async def seed_shopify_catalog(session: AsyncSession) -> dict:
    settings = get_settings()
    result = {
        "products_created": 0,
        "products_skipped": 0,
        "orders_created": 0,
        "orders_skipped": 0,
        "errors": [],
    }
    if not settings.shopify_configured:
        result["errors"].append("Shopify not configured")
        return result

    existing = {p["title"]: p.get("variant_id") for p in await list_seed_products()}
    variant_ids = [vid for vid in existing.values() if vid]

    batch = await _get_or_create_seed_batch(session)
    images = _seed_images()

    for i, fixture in enumerate(SEED_FIXTURES):
        title = SEED_PREFIX + fixture["name"]
        if title in existing:
            result["products_skipped"] += 1
            continue

        image_path = str(images[i % len(images)]) if images else ""
        draft = ProductDraft(
            batch_id=batch.id,
            original_path=image_path or "seed.jpg",
            generated_path=image_path or None,
            name=title,
            price=fixture["price"],
            discount_percent=fixture["discount"],
            quantity=fixture["quantity"],
            price_options_json=[float(fixture["price"])],
            discount_options_json=[fixture["discount"]],
            quantity_options_json=[fixture["quantity"]],
            decision="approved",
            shopify_status="unsent",
        )
        session.add(draft)
        await session.flush()

        sync_result = await sync_product_to_shopify(session, draft)
        if sync_result["status"] == "ok":
            result["products_created"] += 1
            if sync_result.get("variant_id"):
                variant_ids.append(sync_result["variant_id"])
        else:
            result["errors"].append(f"{title}: {sync_result.get('error') or sync_result['status']}")

    await session.commit()
    await ensure_analytics_data(session)

    order_result = await create_demo_orders(variant_ids, count=4)
    result["orders_created"] = order_result["orders_created"]
    result["orders_skipped"] = order_result["orders_skipped"]
    if order_result.get("error"):
        result["errors"].append(f"Orders: {order_result['error']}")

    return result
