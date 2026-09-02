# Composer handoff — dashboard + Shopify demo catalog

The v1 Telegram IMS **already exists**. Do **not** rebuild it. Implement this increment only.

Do not add Next.js, Celery, Redis, Postgres, Docker, or a second app.

Follow Karpathy: minimum code, no speculative features, every step has a verify check.

## Goal

Two complementary seeds so the seller can test **real Shopify** and **analytics** without mixing them accidentally:

1. **Local analytics** (`MockProduct` / `MockSale`) — powers `/dashboard`. Never written to Shopify by `/dashboard`.
2. **Shopify demo catalog** (`/seed-shopify`) — creates **real products** on the Partner dev store using the **same** `create_product()` path as Finish review / `/sync`. Optionally tries a few **demo draft orders** so admin/orders look real. If order APIs fail (missing scopes), products still succeed.

## Locked decisions

| Topic | Decision |
|---|---|
| Dashboard trigger | `/dashboard` + optional prompt. Empty = `"overview"` |
| Dashboard output | Always short-lived `/d/{token}` + 2–4 line Telegram summary |
| Dashboard | Read-only. No Shopify writes |
| Dashboard data | Local mock catalog + mock sales. Label **Demo analytics**. Do not require Shopify Orders API to render charts |
| Shopify catalog | `/seed-shopify` (allowed user only). Uses existing [`src/infrastructure/shopify.py`](src/infrastructure/shopify.py) `create_product` |
| Shopify orders | Best-effort: 3–5 completed **draft orders** against seeded variants. Missing scopes → skip orders, report in Telegram |
| Idempotency | Seed titles prefixed `IMS Seed — `. Skip a title if it already exists on Shopify. Local mock seed: if `MockProduct` count > 0, do not re-insert |
| Text Q&A | Leave [`src/domain/queries.py`](src/domain/queries.py) unchanged |
| Stack | Same FastAPI + SQLite `create_all` + Jinja/CSS |
| Links | Existing `ShortLink` TTL |

## Files

**Extend:** [`src/bot/app.py`](src/bot/app.py), [`src/core/llm.py`](src/core/llm.py), [`src/infrastructure/models.py`](src/infrastructure/models.py), [`src/infrastructure/shopify.py`](src/infrastructure/shopify.py) (optional SKU on variant if cheap; else unique titles only), [`src/web/templates/data.html`](src/web/templates/data.html), [`src/web/static/data.js`](src/web/static/data.js), [`src/web/static/data.css`](src/web/static/data.css).

**Add:** [`src/domain/analytics_seed.py`](src/domain/analytics_seed.py), [`src/domain/dashboard.py`](src/domain/dashboard.py), [`src/domain/shopify_seed.py`](src/domain/shopify_seed.py), [`tests/test_dashboard.py`](tests/test_dashboard.py), [`tests/test_shopify_seed.py`](tests/test_shopify_seed.py).

**README:** one short section: `/dashboard`, `/seed-shopify`, extra scopes `write_draft_orders` (and `read_orders` if required by the mutation you use).

## Part A — local analytics (dashboard)

### Models

`MockProduct`: `id`, `name`, `sku`, `price`, `quantity`, `category`, `source` (`draft` | `fixture`), `draft_id` nullable.

`MockSale`: `id`, `product_id` FK, `qty`, `unit_price`, `sold_at`.

### `ensure_analytics_data(session)`

On `/dashboard` start:

1. If `MockProduct` count is 0:
   - Approved `ProductDraft`s exist → copy to `MockProduct` (`source=draft`) + ~5 sales each over 30 days (deterministic from product id).
   - Else → 12 jewelry/bangle fixtures (`source=fixture`) + ~60 sales. `random.Random(42)` only.
2. If count > 0: no-op.

Cheap extra (optional, keep small): new approved drafts without `draft_id` match get appended + a few sales.

### Snapshot

`build_snapshot(session)` — compact JSON: `as_of`, `inventory[]` (cap 40), `kpis` (units_on_hand, inventory_value, revenue_30d, units_sold_30d, orders_30d), `sales_by_product[]`, `sales_by_day[]` (30 days). Aggregate in Python/SQL. Do not send every sale row to the LLM.

### LLM `build_dashboard_spec(prompt, snapshot)`

JSON object only:

```json
{
  "title": "string",
  "subtitle": "string (mention Demo analytics)",
  "prompt": "string",
  "telegram_summary": "string, max ~500 chars",
  "kpis": [{"label": "string", "value": "string", "hint": "string or empty"}],
  "charts": [{"type": "bar or line", "title": "string", "labels": ["..."], "values": [0], "values_b": null}],
  "tables": [{"title": "string", "columns": ["..."], "rows": [["..."]]}]
}
```

Caps: 6 KPIs, 3 charts, 2 tables, 12 labels, 15 rows. Widgets must follow the prompt. Fallback spec if OpenRouter fails: 4 KPIs + 7-day bars + top-products table.

### `create_dashboard(session, prompt, chat_id)`

seed → snapshot → spec → `create_link(kind="data", payload=spec)` → `{url, telegram_summary}`.

### UI

New payload: banner `Read-only · generated for: {prompt}` + KPIs + charts + tables. Hide empty sections. CSS bars + simple SVG line. Old `{title, columns, rows, chart}` reports still work.

### Bot `/dashboard`

Allowed users only. Prompt = text after command or `"overview"`. Reply summary + URL + localhost/ngrok note if needed.

`/start` add:

- `/dashboard [question] — read-only analytics page (local demo sales)`
- `/seed-shopify — create demo products (and orders if allowed) on the Shopify store`

## Part B — Shopify demo catalog (real store)

### Fixture list (shared names)

~8 jewelry titles, e.g. Gold Bangle Set, Glass Bangles, Kundan Bracelet, Silver Cuff, Pearl Bangle, Temple Jewelry Bangle, Meenakari Bangles, Oxidised Cuff. Prices 9.99–49.99, qty 3–20, discount 0 or 10. **Titles in Shopify must be** `IMS Seed — {name}` so they are obvious and skippable.

Optional images: if `temp/bangle-test-images/*.jpg` exists, attach via existing image upload; if missing, create product without image (do not fail).

### `seed_shopify_catalog(session) -> dict`

Returns `{products_created, products_skipped, orders_created, orders_skipped, errors: []}`.

1. If Shopify not configured → `{..., errors: ["Shopify not configured"]}`.
2. Query existing products (GraphQL `products(first: 50, query: "title:IMS Seed")` or filter in Python). Skip titles already present.
3. For each remaining fixture, build a transient `ProductDraft`-shaped object (or reuse the model without inserting a review batch if easier — inserting a local `ProductDraft` with `decision=approved` and `shopify_status` after create is **preferred** so `/sync` and local inventory stay consistent).
4. Call **`create_product(draft)`** — same function as review finish. Set `shopify_status` / `shopify_product_id` on the local row.
5. After products exist, **try** 3–5 demo orders:
   - Prefer `draftOrderCreate` + `draftOrderComplete` (or the smallest mutation that produces a visible order in admin).
   - Line items: 1–2 seeded variant IDs, qty 1.
   - If GraphQL access denied / userErrors: `orders_skipped` += remaining, append a short error string, **do not** fail product seed.
6. Also call `ensure_analytics_data` if mock tables empty, so `/dashboard` works immediately after seed.

### Bot `/seed-shopify`

Allowed users only. Reply with counts (created / skipped / orders / errors). Warn that this writes to the **dev store**. Idempotent: running twice should skip existing `IMS Seed —` titles.

## Tests

**Dashboard** (`tests/test_dashboard.py`) — mock HTTP, no live Shopify/OpenRouter:

1. `ensure_analytics_data` twice → same product count
2. No drafts → ≥8 mock products and ≥1 sale
3. Fake LLM gets prompt `"low stock"`; payload stores that prompt
4. Fallback spec has kpis + chart or table
5. Expired `/api/data/{token}` → 404

**Shopify seed** (`tests/test_shopify_seed.py`):

1. Not configured → no GraphQL, error message in result
2. Mock `create_product` + mock “already exists” query → second run `products_created==0` and `products_skipped>=1`
3. Order mutation raises → `products_created>=1` (with mocked create) still ok, `orders_created==0`

## Implementation order

1. Mock models + analytics seed + snapshot + dashboard tests 1–2
2. Fallback spec + `create_dashboard` + dashboard tests 3–5
3. data.html/js/css
4. `/dashboard` command
5. `shopify_seed` + tests
6. `/seed-shopify` + README
7. Full `pytest`

## Do not

- Rebuild v1; commit `.env`, `data/`, `temp/`
- Push local `MockSale` rows to Shopify as products
- Make `/dashboard` write to Shopify
- Require order scopes for `/dashboard` or product seed success
- Add dashboard login beyond the unguessable token

## After implementation — what exists and how to test

Tell the operator (and put a short version in README):

**Built**

1. `/dashboard [prompt]` — Telegram → local mock inventory/sales → generated read-only page `/d/{token}`
2. `/seed-shopify` — real products on Shopify titled `IMS Seed — …` via the same create/image path as review; optional demo orders
3. Local `MockProduct`/`MockSale` — dashboard only

**Test matrix**

| What | How | Success |
|---|---|---|
| Local analytics | `/dashboard` then `/dashboard low stock` | Two links; pages differ; KPIs + chart/table; subtitle mentions demo analytics |
| Link expiry | Wait TTL or expire in DB | `/d/{token}` 404 |
| Shopify products | `/seed-shopify` then [admin Products](https://admin.shopify.com/store/ims-dev-store-s8ak7vex/products) | New `IMS Seed —` rows; second `/seed-shopify` skips them |
| Same product pipeline | Telegram photo → approve → Finish | Product **without** `IMS Seed —` prefix appears in admin (real flow) |
| Demo orders | After seed, admin **Orders** | 3–5 orders **or** Telegram says orders skipped (scopes) |
| Isolation | `/dashboard` after seed | Charts still from **local** mock sales, not Shopify order totals (unless you later add Shopify reads — **do not** in this increment) |

**Not in this increment:** live Shopify order totals on the dashboard; storefront password is still a Shopify admin setting.
