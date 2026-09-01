import logging
from contextlib import asynccontextmanager
from pathlib import Path

from src.core.config import get_settings

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.api.data import router as data_router
from src.api.media import router as media_router
from src.api.review import router as review_router
from src.bot.app import build_bot_application
from src.infrastructure.database import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "web" / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    await init_db()
    bot_app = build_bot_application()
    if bot_app:
        await bot_app.initialize()
        await bot_app.start()
        await bot_app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram bot polling started")
    yield
    if bot_app:
        await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(title="Shopify IMS", lifespan=lifespan)
    app.include_router(review_router)
    app.include_router(data_router)
    app.include_router(media_router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=False)
