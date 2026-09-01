import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.infrastructure.models import ShortLink


async def create_link(
    session: AsyncSession,
    *,
    kind: str,
    telegram_chat_id: int | None = None,
    payload: dict | None = None,
    ttl_hours: int | None = None,
) -> ShortLink:
    settings = get_settings()
    hours = ttl_hours if ttl_hours is not None else settings.link_ttl_hours
    if ttl_hours is None and settings.link_ttl_minutes > 0:
        delta = timedelta(minutes=settings.link_ttl_minutes)
    else:
        delta = timedelta(hours=hours or 24)
    link = ShortLink(
        token=str(uuid.uuid4()),
        kind=kind,
        expires_at=datetime.now(timezone.utc) + delta,
        payload_json=payload,
        telegram_chat_id=telegram_chat_id,
    )
    session.add(link)
    await session.flush()
    return link


async def get_valid_link(session: AsyncSession, token: str, kind: str | None = None) -> ShortLink | None:
    result = await session.execute(select(ShortLink).where(ShortLink.token == token))
    link = result.scalar_one_or_none()
    if link is None:
        return None
    expires = link.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= datetime.now(timezone.utc):
        return None
    if kind is not None and link.kind != kind:
        return None
    return link


async def expire_link(session: AsyncSession, link: ShortLink) -> None:
    link.expires_at = datetime.now(timezone.utc)
    await session.flush()
