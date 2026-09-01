import asyncio
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.core.config import get_settings
from src.infrastructure.models import Base
from src.main import create_app

TEST_DB = "sqlite+aiosqlite:///./data/test.db"


@pytest.fixture(autouse=True)
def _test_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", TEST_DB)
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("SHOPIFY_STORE_DOMAIN", "")
    monkeypatch.setenv("SHOPIFY_CLIENT_ID", "")
    monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", "")
    monkeypatch.setenv("SHOPIFY_ADMIN_ACCESS_TOKEN", "")
    get_settings.cache_clear()


@pytest.fixture
def upload_dir(tmp_path):
    return tmp_path / "uploads"


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(TEST_DB)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture(autouse=True)
async def bind_db(engine, monkeypatch):
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def init_db():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    monkeypatch.setattr("src.infrastructure.database.engine", engine)
    monkeypatch.setattr("src.infrastructure.database.async_session_factory", factory)
    monkeypatch.setattr("src.infrastructure.database.init_db", init_db)


@pytest_asyncio.fixture
async def session(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess


@pytest_asyncio.fixture
async def client(monkeypatch):
    monkeypatch.setattr("src.main.build_bot_application", lambda: None)
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
