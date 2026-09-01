import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.models import MockProduct, MockSale, ProductDraft

FIXTURE_PRODUCTS = [
    ("Gold Bangle Set", "BNG-001", Decimal("29.99"), 12, "Bangles"),
    ("Glass Bangles", "BNG-002", Decimal("9.99"), 20, "Bangles"),
    ("Kundan Bracelet", "BNG-003", Decimal("39.99"), 8, "Bracelets"),
    ("Silver Cuff", "BNG-004", Decimal("24.99"), 15, "Cuffs"),
    ("Pearl Bangle", "BNG-005", Decimal("19.99"), 10, "Bangles"),
    ("Temple Jewelry Bangle", "BNG-006", Decimal("49.99"), 6, "Bangles"),
    ("Meenakari Bangles", "BNG-007", Decimal("34.99"), 9, "Bangles"),
    ("Oxidised Cuff", "BNG-008", Decimal("14.99"), 18, "Cuffs"),
    ("Lac Bangle Pair", "BNG-009", Decimal("12.99"), 14, "Bangles"),
    ("Antique Gold Bangle", "BNG-010", Decimal("44.99"), 5, "Bangles"),
    ("Stone Studded Bangle", "BNG-011", Decimal("27.99"), 11, "Bangles"),
    ("Brass Kada", "BNG-012", Decimal("16.99"), 16, "Cuffs"),
]


def _sale_dates(rng: random.Random, count: int) -> list[datetime]:
    now = datetime.now(timezone.utc)
    return [now - timedelta(days=rng.randint(0, 29), hours=rng.randint(0, 23)) for _ in range(count)]


async def _add_sales(session: AsyncSession, product: MockProduct, rng: random.Random, count: int) -> None:
    for i, sold_at in enumerate(_sale_dates(rng, count)):
        qty = 1 + (product.id + i) % 3
        session.add(
            MockSale(
                product_id=product.id,
                qty=qty,
                unit_price=product.price,
                sold_at=sold_at,
            )
        )


async def ensure_analytics_data(session: AsyncSession) -> None:
    count = await session.scalar(select(func.count()).select_from(MockProduct))
    if count and count > 0:
        await _append_new_drafts(session)
        return

    approved = await session.execute(
        select(ProductDraft).where(ProductDraft.decision == "approved").order_by(ProductDraft.id)
    )
    drafts = list(approved.scalars())
    if drafts:
        for d in drafts:
            mp = MockProduct(
                name=d.name,
                sku=f"DRF-{d.id:04d}",
                price=d.price,
                quantity=d.quantity,
                category="Bangles",
                source="draft",
                draft_id=d.id,
            )
            session.add(mp)
            await session.flush()
            rng = random.Random(d.id * 9973)
            await _add_sales(session, mp, rng, 5)
    else:
        rng = random.Random(42)
        for name, sku, price, qty, category in FIXTURE_PRODUCTS:
            mp = MockProduct(
                name=name,
                sku=sku,
                price=price,
                quantity=qty,
                category=category,
                source="fixture",
            )
            session.add(mp)
            await session.flush()
            await _add_sales(session, mp, rng, rng.randint(4, 6))
    await session.commit()


async def _append_new_drafts(session: AsyncSession) -> None:
    approved = await session.execute(
        select(ProductDraft).where(ProductDraft.decision == "approved").order_by(ProductDraft.id)
    )
    for d in approved.scalars():
        exists = await session.scalar(
            select(func.count()).select_from(MockProduct).where(MockProduct.draft_id == d.id)
        )
        if exists:
            continue
        mp = MockProduct(
            name=d.name,
            sku=f"DRF-{d.id:04d}",
            price=d.price,
            quantity=d.quantity,
            category="Bangles",
            source="draft",
            draft_id=d.id,
        )
        session.add(mp)
        await session.flush()
        rng = random.Random(d.id * 9973)
        await _add_sales(session, mp, rng, 5)
    await session.commit()


async def build_snapshot(session: AsyncSession) -> dict:
    products = list((await session.execute(select(MockProduct).limit(40))).scalars())
    sales = list((await session.execute(select(MockSale))).scalars())
    product_map = {p.id: p for p in products}
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=30)

    units_on_hand = sum(p.quantity for p in products)
    inventory_value = float(sum(p.price * p.quantity for p in products))

    recent_sales = [s for s in sales if s.sold_at.replace(tzinfo=timezone.utc) >= cutoff]
    revenue_30d = float(sum(s.qty * s.unit_price for s in recent_sales))
    units_sold_30d = sum(s.qty for s in recent_sales)
    orders_30d = len(recent_sales)

    by_product: dict[int, dict] = {}
    for s in recent_sales:
        p = product_map.get(s.product_id)
        if not p:
            continue
        entry = by_product.setdefault(p.id, {"name": p.name, "units": 0, "revenue": 0.0})
        entry["units"] += s.qty
        entry["revenue"] += float(s.qty * s.unit_price)

    by_day: dict[str, dict] = {}
    for s in recent_sales:
        day = s.sold_at.date().isoformat()
        entry = by_day.setdefault(day, {"day": day, "revenue": 0.0, "units": 0})
        entry["revenue"] += float(s.qty * s.unit_price)
        entry["units"] += s.qty

    sales_by_day = sorted(by_day.values(), key=lambda x: x["day"])[-30:]
    sales_by_product = sorted(by_product.values(), key=lambda x: x["revenue"], reverse=True)[:20]

    return {
        "as_of": now.isoformat(),
        "inventory": [
            {
                "name": p.name,
                "sku": p.sku,
                "qty": p.quantity,
                "price": float(p.price),
                "category": p.category,
            }
            for p in products
        ],
        "kpis": {
            "units_on_hand": units_on_hand,
            "inventory_value": round(inventory_value, 2),
            "revenue_30d": round(revenue_30d, 2),
            "units_sold_30d": units_sold_30d,
            "orders_30d": orders_30d,
        },
        "sales_by_product": sales_by_product,
        "sales_by_day": sales_by_day,
    }
