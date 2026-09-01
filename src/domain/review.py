from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.domain.batches import get_batch_by_review_token
from src.domain.links import expire_link, get_valid_link
from src.infrastructure.models import ProductDraft, SwipeEvent
from src.domain.inventory import sync_product_to_shopify


async def get_review_payload(session: AsyncSession, token: str) -> dict | None:
    settings = get_settings()
    link = await get_valid_link(session, token, kind="review")
    if link is None:
        return None
    batch = await get_batch_by_review_token(session, token)
    if batch is None:
        return None
    products = []
    for p in batch.products:
        products.append(
            {
                "id": p.id,
                "original_image_url": f"/media/{token}/{p.id}/original",
                "generated_image_url": f"/media/{token}/{p.id}/generated",
                "image_url": f"/media/{token}/{p.id}/generated",
                "name": p.name,
                "price": float(p.price),
                "discount_percent": p.discount_percent,
                "quantity": p.quantity,
                "options": {
                    "price": p.price_options_json,
                    "discount": p.discount_options_json,
                    "quantity": p.quantity_options_json,
                },
                "decision": p.decision,
                "generation_failed": p.generation_failed,
            }
        )
    return {
        "expires_at": link.expires_at.isoformat(),
        "expires_in_minutes": settings.link_ttl_minutes,
        "products": products,
    }


async def update_product(
    session: AsyncSession,
    token: str,
    product_id: int,
    *,
    name: str | None = None,
    price: float | None = None,
    discount_percent: int | None = None,
    quantity: int | None = None,
) -> ProductDraft | None:
    link = await get_valid_link(session, token, kind="review")
    if link is None:
        return None
    result = await session.execute(select(ProductDraft).where(ProductDraft.id == product_id))
    product = result.scalar_one_or_none()
    if product is None:
        return None
    if name is not None:
        product.name = name
    if price is not None:
        product.price = Decimal(str(price))
    if discount_percent is not None:
        product.discount_percent = discount_percent
    if quantity is not None:
        product.quantity = quantity
    await session.commit()
    return product


async def record_swipe(
    session: AsyncSession,
    token: str,
    product_id: int,
    *,
    direction: str,
    dx: int,
    dy: int,
    client_ts: int | None = None,
) -> ProductDraft | None:
    link = await get_valid_link(session, token, kind="review")
    if link is None:
        return None
    result = await session.execute(select(ProductDraft).where(ProductDraft.id == product_id))
    product = result.scalar_one_or_none()
    if product is None:
        return None
    event = SwipeEvent(
        product_id=product_id,
        direction=direction,
        dx=dx,
        dy=dy,
        client_ts=client_ts,
    )
    session.add(event)
    product.decision = "approved" if direction == "right" else "rejected"
    await session.commit()
    return product


async def finish_review(session: AsyncSession, token: str) -> dict:
    link = await get_valid_link(session, token, kind="review")
    if link is None:
        return {"error": "not_found"}
    batch = await get_batch_by_review_token(session, token)
    if batch is None:
        return {"error": "not_found"}

    approved = 0
    rejected = 0
    skipped = 0
    ok = 0
    errors = 0

    for product in batch.products:
        if product.decision == "approved":
            approved += 1
            result = await sync_product_to_shopify(session, product)
            if result["status"] == "ok":
                ok += 1
            elif result["status"] == "skipped":
                skipped += 1
            else:
                errors += 1
        elif product.decision == "rejected":
            rejected += 1
        else:
            product.decision = "rejected"
            rejected += 1

    await expire_link(session, link)
    await session.commit()
    return {
        "approved": approved,
        "rejected": rejected,
        "shopify_ok": ok,
        "shopify_skipped": skipped,
        "shopify_errors": errors,
        "telegram_chat_id": batch.telegram_chat_id,
    }


async def get_product_for_media(
    session: AsyncSession, token: str, product_id: int, variant: str = "generated"
) -> tuple[ProductDraft | None, str | None]:
    link = await get_valid_link(session, token, kind="review")
    if link is None:
        return None, None
    batch = await get_batch_by_review_token(session, token)
    if batch is None:
        return None, None
    result = await session.execute(
        select(ProductDraft).where(
            ProductDraft.id == product_id,
            ProductDraft.batch_id == batch.id,
        )
    )
    product = result.scalar_one_or_none()
    if product is None:
        return None, None
    if variant == "original":
        return product, product.original_path
    if variant == "generated":
        path = product.generated_path or product.original_path
        return product, path
    return None, None
