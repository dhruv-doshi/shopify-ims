from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.notifications import format_finish_summary, send_telegram_message
from src.domain.links import get_valid_link
from src.domain.review import finish_review, get_review_payload, record_swipe, update_product
from src.infrastructure.database import get_db

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "web" / "templates"))


class ProductUpdate(BaseModel):
    name: str | None = None
    price: float | None = None
    discount_percent: int | None = None
    quantity: int | None = None


class SwipeBody(BaseModel):
    direction: str
    dx: int = 0
    dy: int = 0
    client_ts: int | None = None


@router.get("/r/{token}", response_class=HTMLResponse)
async def review_page(request: Request, token: str, db: AsyncSession = Depends(get_db)):
    link = await get_valid_link(db, token, kind="review")
    if link is None:
        raise HTTPException(status_code=404, detail="Link not found or expired")
    return templates.TemplateResponse(request, "review.html", {"token": token})


@router.get("/api/review/{token}")
async def review_data(token: str, db: AsyncSession = Depends(get_db)):
    payload = await get_review_payload(db, token)
    if payload is None:
        raise HTTPException(status_code=404, detail="Link not found or expired")
    return payload


@router.patch("/api/review/{token}/products/{product_id}")
async def patch_product(
    token: str,
    product_id: int,
    body: ProductUpdate,
    db: AsyncSession = Depends(get_db),
):
    product = await update_product(
        db,
        token,
        product_id,
        name=body.name,
        price=body.price,
        discount_percent=body.discount_percent,
        quantity=body.quantity,
    )
    if product is None:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}


@router.post("/api/review/{token}/products/{product_id}/swipe")
async def swipe_product(
    token: str,
    product_id: int,
    body: SwipeBody,
    db: AsyncSession = Depends(get_db),
):
    if body.direction not in ("left", "right"):
        raise HTTPException(status_code=400, detail="Invalid direction")
    product = await record_swipe(
        db,
        token,
        product_id,
        direction=body.direction,
        dx=body.dx,
        dy=body.dy,
        client_ts=body.client_ts,
    )
    if product is None:
        raise HTTPException(status_code=404, detail="Not found")
    return {"decision": product.decision}


@router.post("/api/review/{token}/finish")
async def finish(token: str, db: AsyncSession = Depends(get_db)):
    result = await finish_review(db, token)
    if result.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="Not found")
    chat_id = result.get("telegram_chat_id")
    if chat_id:
        await send_telegram_message(chat_id, format_finish_summary(result))
    return result
