from src.core.config import get_settings
from src.core.llm import build_dashboard_spec
from src.domain.analytics_seed import build_snapshot, ensure_analytics_data
from src.domain.links import create_link
from sqlalchemy.ext.asyncio import AsyncSession

DEMO_SUBTITLE = (
    "Live inventory from Shopify · sales charts use demo analytics (not Shopify orders)"
)
LOCAL_SUBTITLE = (
    "Demo analytics — local mock inventory and sales (not Shopify)"
)


def _dashboard_subtitle(snapshot: dict) -> str:
    if snapshot.get("inventory_source") == "shopify":
        return DEMO_SUBTITLE
    return LOCAL_SUBTITLE


def _enrich_spec(spec: dict, snapshot: dict, prompt: str) -> dict:
    spec["prompt"] = prompt
    spec["subtitle"] = spec.get("subtitle") or _dashboard_subtitle(snapshot)
    spec["as_of"] = snapshot["as_of"]
    spec["product_count"] = snapshot.get("product_count", len(snapshot.get("inventory") or []))
    spec["inventory_source"] = snapshot.get("inventory_source", "local")
    spec["low_stock_count"] = snapshot.get("low_stock_count", 0)
    spec["quick_prompts"] = ["overview", "low stock", "top sellers"]
    spec["snapshot"] = {
        "inventory": snapshot.get("inventory") or [],
        "sales_by_product": snapshot.get("sales_by_product") or [],
        "sales_by_day": snapshot.get("sales_by_day") or [],
        "kpis": snapshot.get("kpis") or {},
    }
    return spec


async def create_dashboard(session: AsyncSession, prompt: str, chat_id: int) -> dict:
    settings = get_settings()
    await ensure_analytics_data(session)
    snapshot = await build_snapshot(session)
    spec = await build_dashboard_spec(prompt, snapshot)
    spec = _enrich_spec(spec, snapshot, prompt)
    link = await create_link(session, kind="data", telegram_chat_id=chat_id, payload=spec)
    await session.commit()
    source_note = "live Shopify inventory" if snapshot.get("inventory_source") == "shopify" else "local demo data"
    summary = spec.get("telegram_summary") or (
        f"Dashboard ready ({source_note}). {snapshot.get('product_count', 0)} products · "
        f"{snapshot.get('low_stock_count', 0)} low stock."
    )
    return {
        "url": f"{settings.app_public_url}/d/{link.token}",
        "telegram_summary": summary,
        "inventory_source": snapshot.get("inventory_source", "local"),
        "product_count": snapshot.get("product_count", 0),
    }
