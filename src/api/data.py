from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.links import get_valid_link
from src.infrastructure.database import get_db

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "web" / "templates"))


@router.get("/d/{token}", response_class=HTMLResponse)
async def data_page(request: Request, token: str, db: AsyncSession = Depends(get_db)):
    link = await get_valid_link(db, token, kind="data")
    if link is None:
        raise HTTPException(status_code=404, detail="Link not found or expired")
    return templates.TemplateResponse(request, "data.html", {"token": token})


@router.get("/api/data/{token}")
async def data_json(token: str, db: AsyncSession = Depends(get_db)):
    link = await get_valid_link(db, token, kind="data")
    if link is None:
        raise HTTPException(status_code=404, detail="Link not found or expired")
    return link.payload_json or {}
