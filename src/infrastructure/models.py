import json
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Numeric


class Base(DeclarativeBase):
    pass


class ShortLink(Base):
    __tablename__ = "short_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(16))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    telegram_chat_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    batches: Mapped[list["Batch"]] = relationship(back_populates="review_link")


class Batch(Base):
    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(Integer)
    telegram_chat_id: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="collecting")
    review_link_id: Mapped[int | None] = mapped_column(ForeignKey("short_links.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    review_link: Mapped["ShortLink | None"] = relationship(back_populates="batches")
    products: Mapped[list["ProductDraft"]] = relationship(back_populates="batch")


class ProductDraft(Base):
    __tablename__ = "product_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"))
    original_path: Mapped[str] = mapped_column(String(512))
    generated_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    generation_failed: Mapped[bool] = mapped_column(default=False)
    name: Mapped[str] = mapped_column(String(256), default="Untitled product")
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("9.99"))
    discount_percent: Mapped[int] = mapped_column(Integer, default=0)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    price_options_json: Mapped[list] = mapped_column(JSON, default=list)
    discount_options_json: Mapped[list] = mapped_column(JSON, default=list)
    quantity_options_json: Mapped[list] = mapped_column(JSON, default=list)
    decision: Mapped[str] = mapped_column(String(16), default="pending")
    shopify_status: Mapped[str] = mapped_column(String(16), default="unsent")
    shopify_product_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    shopify_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    batch: Mapped["Batch"] = relationship(back_populates="products")
    swipes: Mapped[list["SwipeEvent"]] = relationship(back_populates="product")


class SwipeEvent(Base):
    __tablename__ = "swipe_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product_drafts.id"))
    direction: Mapped[str] = mapped_column(String(8))
    dx: Mapped[int] = mapped_column(Integer, default=0)
    dy: Mapped[int] = mapped_column(Integer, default=0)
    client_ts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    product: Mapped["ProductDraft"] = relationship(back_populates="swipes")


def dumps_options(values: list) -> list:
    return json.loads(json.dumps(values))
