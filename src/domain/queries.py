from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.llm import answer_inventory_question
from src.domain.links import create_link
from src.infrastructure.models import ProductDraft


async def load_inventory_rows(session: AsyncSession) -> list[dict]:
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
            }
        )
    return rows


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
    rows = await load_inventory_rows(session)
    if not rows:
        return {"mode": "text", "text": "No inventory data available yet."}

    answer = await answer_inventory_question(question, rows)
    if should_overflow(answer, question):
        payload = {
            "title": answer.get("title") or "Inventory report",
            "columns": answer.get("columns") or ["name", "price", "quantity", "decision"],
            "rows": answer.get("rows") or [[r["name"], r["price"], r["quantity"], r["decision"]] for r in rows],
            "chart": answer.get("chart"),
            "summary": answer.get("telegram_text") or "",
        }
        link = await create_link(session, kind="data", telegram_chat_id=chat_id, payload=payload)
        await session.commit()
        return {
            "mode": "link",
            "url": f"{settings.app_public_url}/d/{link.token}",
        }

    return {
        "mode": "text",
        "text": answer.get("telegram_text") or "No answer.",
    }
