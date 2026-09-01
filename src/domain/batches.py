import asyncio
import logging
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.config import get_settings
from src.core.image_io import is_valid_image, write_image
from src.core.images import generate_product_shot
from src.core.llm import analyze_product_image
from src.domain.links import create_link
from src.infrastructure.models import Batch, ProductDraft, ShortLink

logger = logging.getLogger(__name__)


@dataclass
class PhotoInput:
    bytes: bytes
    mime: str
    filename: str


def upload_root() -> Path:
    return Path(get_settings().upload_dir)


async def create_batch(session: AsyncSession, user_id: int, chat_id: int) -> Batch:
    batch = Batch(telegram_user_id=user_id, telegram_chat_id=chat_id, status="collecting")
    session.add(batch)
    await session.flush()
    return batch


async def save_original(batch_id: int, index: int, photo: PhotoInput) -> Path:
    if not is_valid_image(photo.bytes):
        raise ValueError("Telegram photo is not a valid image file")
    ext = Path(photo.filename).suffix or ".jpg"
    path = upload_root() / str(batch_id) / f"original_{index}{ext}"
    return write_image(path, photo.bytes)


async def _process_one(
    session: AsyncSession,
    batch_id: int,
    index: int,
    photo: PhotoInput,
    *,
    vision_fn=analyze_product_image,
    image_fn=generate_product_shot,
) -> ProductDraft:
    original_path = await save_original(batch_id, index, photo)
    analysis = await vision_fn(photo.bytes, photo.mime)
    generated_path = original_path.parent / f"generated_{index}.jpg"
    saved_generated = await image_fn(photo.bytes, generated_path, photo.mime)
    ok = saved_generated is not None
    draft = ProductDraft(
        batch_id=batch_id,
        original_path=str(original_path),
        generated_path=str(saved_generated) if ok else None,
        generation_failed=not ok,
        name=analysis["name"],
        price=Decimal(str(analysis["price_options"][0])),
        discount_percent=int(analysis["discount_options"][0]),
        quantity=int(analysis["quantity_options"][0]),
        price_options_json=analysis["price_options"],
        discount_options_json=analysis["discount_options"],
        quantity_options_json=analysis["quantity_options"],
    )
    session.add(draft)
    await session.flush()
    return draft


async def process_batch(
    session: AsyncSession,
    batch_id: int,
    photos: list[PhotoInput],
    *,
    vision_fn=analyze_product_image,
    image_fn=generate_product_shot,
) -> str:
    settings = get_settings()
    result = await session.execute(select(Batch).where(Batch.id == batch_id))
    batch = result.scalar_one()
    batch.status = "processing"
    await session.flush()

    sem = asyncio.Semaphore(settings.image_concurrency)

    async def run(index: int, photo: PhotoInput) -> ProductDraft:
        async with sem:
            return await _process_one(
                session, batch_id, index, photo, vision_fn=vision_fn, image_fn=image_fn
            )

    try:
        await asyncio.gather(*(run(i, p) for i, p in enumerate(photos)))
        link = await create_link(session, kind="review", telegram_chat_id=batch.telegram_chat_id)
        batch.review_link_id = link.id
        batch.status = "ready"
        await session.commit()
        return link.token
    except Exception:
        logger.exception("Batch %s failed", batch_id)
        batch.status = "failed"
        await session.commit()
        raise


async def get_batch_by_review_token(session: AsyncSession, token: str) -> Batch | None:
    result = await session.execute(
        select(Batch)
        .join(ShortLink, Batch.review_link_id == ShortLink.id)
        .where(ShortLink.token == token)
        .options(selectinload(Batch.products), selectinload(Batch.review_link))
    )
    return result.scalar_one_or_none()
