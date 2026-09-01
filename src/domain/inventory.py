from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.models import ProductDraft
from src.infrastructure.shopify import create_product


async def sync_product_to_shopify(session: AsyncSession, product: ProductDraft) -> dict:
    if product.decision != "approved":
        return {"status": "skipped", "error": "not approved"}
    if product.shopify_status == "ok" and product.shopify_product_id:
        return {
            "status": "ok",
            "product_id": product.shopify_product_id,
            "variant_id": None,
            "error": None,
        }

    result = await create_product(product)
    product.shopify_status = result["status"]
    product.shopify_product_id = result.get("product_id")
    product.shopify_error = result.get("error")
    await session.flush()
    return result


async def sync_unsent_products(session: AsyncSession) -> dict:
    result = await session.execute(
        select(ProductDraft).where(
            ProductDraft.decision == "approved",
            ProductDraft.shopify_status.in_(("unsent", "error")),
        )
    )
    products = list(result.scalars())
    ok = errors = skipped = 0
    for product in products:
        res = await sync_product_to_shopify(session, product)
        if res["status"] == "ok":
            ok += 1
        elif res["status"] == "skipped":
            skipped += 1
        else:
            errors += 1
    await session.commit()
    return {"total": len(products), "ok": ok, "errors": errors, "skipped": skipped}
