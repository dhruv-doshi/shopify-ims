from src.core.config import get_settings
from src.core.llm import build_dashboard_spec
from src.domain.analytics_seed import build_snapshot, ensure_analytics_data
from src.domain.links import create_link
from sqlalchemy.ext.asyncio import AsyncSession


async def create_dashboard(session: AsyncSession, prompt: str, chat_id: int) -> dict:
    settings = get_settings()
    await ensure_analytics_data(session)
    snapshot = await build_snapshot(session)
    spec = await build_dashboard_spec(prompt, snapshot)
    spec["prompt"] = prompt
    link = await create_link(session, kind="data", telegram_chat_id=chat_id, payload=spec)
    await session.commit()
    return {
        "url": f"{settings.app_public_url}/d/{link.token}",
        "telegram_summary": spec.get("telegram_summary") or "Dashboard ready.",
    }
