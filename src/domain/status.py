from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.infrastructure.models import Batch, ProductDraft
from src.infrastructure.shopify import list_inventory_products


async def collect_status(session: AsyncSession) -> dict:
    settings = get_settings()
    shopify_configured = settings.shopify_configured
    shopify_ok = False
    product_count = 0
    shopify_error = None

    if shopify_configured:
        try:
            rows = await list_inventory_products()
            product_count = len(rows)
            shopify_ok = True
        except Exception as exc:
            shopify_error = str(exc)

    unsent = await session.scalar(
        select(func.count())
        .select_from(ProductDraft)
        .where(
            ProductDraft.decision == "approved",
            ProductDraft.shopify_status.in_(("unsent", "error")),
        )
    )

    last = (
        await session.execute(
            select(Batch).where(Batch.status != "seed").order_by(Batch.id.desc()).limit(1)
        )
    ).scalar_one_or_none()

    return {
        "shopify_configured": shopify_configured,
        "shopify_ok": shopify_ok,
        "shopify_error": shopify_error,
        "product_count": product_count,
        "unsent_drafts": int(unsent or 0),
        "last_batch_id": last.id if last else None,
        "last_batch_status": last.status if last else None,
    }


def format_status(data: dict) -> str:
    if not data["shopify_configured"]:
        shopify_line = "Shopify: not configured"
    elif data["shopify_ok"]:
        shopify_line = f"Shopify: OK · {data['product_count']} products"
    else:
        err = data.get("shopify_error") or "unreachable"
        shopify_line = f"Shopify: configured but failed ({err})"

    if data["last_batch_id"] is None:
        batch_line = "Last batch: none"
    else:
        batch_line = f"Last batch: #{data['last_batch_id']} ({data['last_batch_status']})"

    return "\n".join(
        [
            shopify_line,
            f"Unsent approved drafts: {data['unsent_drafts']}",
            batch_line,
        ]
    )
