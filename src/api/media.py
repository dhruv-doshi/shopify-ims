from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.review import get_product_for_media
from src.infrastructure.database import get_db

router = APIRouter()


def _media_type(path: Path) -> str:
    if path.suffix.lower() == ".png":
        return "image/png"
    return "image/jpeg"


@router.get("/media/{token}/{product_id}/{variant}")
async def serve_media_variant(
    token: str, product_id: int, variant: str, db: AsyncSession = Depends(get_db)
):
    if variant not in ("original", "generated"):
        raise HTTPException(status_code=404, detail="Not found")
    product, path_str = await get_product_for_media(db, token, product_id, variant=variant)
    if product is None or not path_str:
        raise HTTPException(status_code=404, detail="Not found")
    path = Path(path_str)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing")
    return FileResponse(path, media_type=_media_type(path))


@router.get("/media/{token}/{product_id}")
async def serve_media(token: str, product_id: int, db: AsyncSession = Depends(get_db)):
    product, path_str = await get_product_for_media(db, token, product_id, variant="generated")
    if product is None or not path_str:
        raise HTTPException(status_code=404, detail="Not found")
    path = Path(path_str)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing")
    return FileResponse(path, media_type=_media_type(path))
