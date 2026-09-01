import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.llm import answer_inventory_question
from src.domain.links import create_link
from src.infrastructure.models import ProductDraft
from src.infrastructure.shopify import list_inventory_products

logger = logging.getLogger(__name__)


async def _load_local_rows(session: AsyncSession) -> list[dict]:
    result = await session.execute(
        select(ProductDraft).order_by(ProductDraft.created_at.desc()).limit(200)
    )
    rows = []
    for p in result.scalars():
        rows.append(
            {
                "id": p.id,
                "name": p.name,
                "price": float(p.price),
                "discount_percent": p.discount_percent,
                "quantity": p.quantity,
                "decision": p.decision,
                "shopify_status": p.shopify_status,
                "source": "local",
            }
        )
    return rows


async def load_inventory_rows(session: AsyncSession) -> list[dict]:
    settings = get_settings()
    if settings.shopify_configured:
        try:
            return await list_inventory_products()
        except Exception as exc:
            logger.warning("Shopify inventory fetch failed: %s", exc)
            raise
    return await _load_local_rows(session)


def should_overflow(answer: dict, question: str) -> bool:
    rows = answer.get("rows") or []
    text = answer.get("telegram_text") or ""
    q = question.lower()
    if len(rows) > 8:
        return True
    if any(word in q for word in ("chart", "graph", "breakdown")):
        return True
    if len(text) > 1500:
        return True
    if answer.get("mode") == "link":
        return True
    return False


async def handle_question(session: AsyncSession, question: str, chat_id: int) -> dict:
    settings = get_settings()
    try:
        rows = await load_inventory_rows(session)
    except Exception as exc:
        return {
            "mode": "text",
            "text": f"Could not load inventory from Shopify: {exc}",
        }

    if not rows:
        if settings.shopify_configured:
            return {"mode": "text", "text": "Live Shopify: 0 products\nYour Shopify store has no products yet."}
        return {"mode": "text", "text": "Local drafts: 0 products\nNo inventory data available yet."}

    source = rows[0].get("source", "local")
    prefix = (
        f"Live Shopify: {len(rows)} products"
        if source == "shopify"
        else f"Local drafts: {len(rows)} products"
    )
    answer = await answer_inventory_question(question, rows, source=source)
    if should_overflow(answer, question):
        payload = {
            "title": answer.get("title") or "Inventory report",
            "columns": answer.get("columns") or ["name", "price", "quantity", "status"],
            "rows": answer.get("rows")
            or [[r["name"], r["price"], r["quantity"], r.get("decision", r.get("shopify_status"))] for r in rows],
            "chart": answer.get("chart"),
            "summary": answer.get("telegram_text") or "",
        }
        link = await create_link(session, kind="data", telegram_chat_id=chat_id, payload=payload)
        await session.commit()
        url = f"{settings.app_public_url}/d/{link.token}"
        return {
            "mode": "link",
            "url": url,
            "text": f"{prefix}\nReport ready: {url}",
        }

    body = answer.get("telegram_text") or "No answer."
    return {
        "mode": "text",
        "text": f"{prefix}\n{body}",
    }
