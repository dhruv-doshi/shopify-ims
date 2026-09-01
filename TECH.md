# Technical document — Shopify IMS

Single FastAPI process: Telegram polling bot, OpenRouter (vision + image gen + dashboard JSON), SQLite, Jinja review/dashboard pages, Shopify Admin GraphQL.

## Stack

| Layer | Choice |
|---|---|
| Runtime | Python 3.11+, one process (`python -m src.main`) |
| HTTP | FastAPI + Uvicorn |
| Bot | `python-telegram-bot` **polling** (not webhooks) |
| DB | SQLite via SQLAlchemy 2 async + aiosqlite (`data/app.db`) |
| LLM / images | OpenRouter (`OPENROUTER_VISION_MODEL`, `OPENROUTER_IMAGE_MODEL`) |
| Shopify | Admin GraphQL + client-credentials OAuth (`src/infrastructure/shopify_auth.py`) |
| UI | Jinja templates + vanilla JS/CSS (`src/web/`) |
| Links | Unguessable UUID tokens with TTL (`LINK_TTL_MINUTES`, default 60) |

No Next.js, Redis, Postgres, Celery, or embedded Shopify admin app.

## Layout

```
src/main.py                 FastAPI app + lifespan (DB, bot polling)
src/bot/                    Telegram handlers, photo debounce, command menu
src/domain/                 Batches, review, inventory sync, Q&A, dashboard, seed, status
src/infrastructure/         SQLAlchemy models, Shopify GraphQL, auth, DB session
src/core/                   Settings, OpenRouter LLM/images, image validation
src/api/                    /r /d /media JSON + HTML
src/web/                    review.html, data.html, static JS/CSS
```

## Persistence

`init_db()` runs `create_all` on startup.

| Table | Role |
|---|---|
| `short_links` | Review (`kind=review`) and data (`kind=data`) pages; payload JSON; expiry |
| `batches` | One photo batch (or `status=seed` for `/seed_shopify`) |
| `product_drafts` | Autofill + decisions + Shopify push status |
| `swipe_events` | Review gestures |
| `mock_products` / `mock_sales` | Dashboard **demo sales** only; never written to Shopify by `/dashboard` |

Uploads live under `UPLOAD_DIR` (`data/uploads/{batch_id}/`).

## Data flow

### 1. Add products (photos)

```
Telegram photos → PhotoBatcher (~3s idle)
  → create Batch + save images
  → OpenRouter vision (name/price/discount/qty options)
  → OpenRouter image gen (product shot)
  → ShortLink kind=review
  → Telegram: /r/{token}
```

Seller edits chips, swipes approve/reject. **Finish review**:

```
approved drafts → create_product() (Shopify GraphQL)
  → expire review link
  → Telegram summary + “Review link is now closed.”
```

`/sync` retries `decision=approved` and `shopify_status` in `unsent|error`.

### 2. Inventory Q&A (text)

```
Telegram text (not a command)
  → if Shopify configured: products(first: 100) GraphQL
  → else: local ProductDraft rows
  → OpenRouter JSON answer
  → short text in chat, or /d/{token} for large tables
```

Replies are prefixed `Live Shopify: N products` or `Local drafts: N products`.

### 3. Dashboard

```
/dashboard [prompt]
  → ensure MockProduct/MockSale exist (fixtures or copies of approved drafts)
  → snapshot: Shopify inventory when configured + local mock sales (30d)
  → OpenRouter dashboard spec (or fallback KPIs/charts/tables)
  → ShortLink kind=data
  → Telegram: “Demo sales charts · live inventory” (or local) + URL
```

The data page (`/d/{token}`) shows KPIs, charts, tables, Overview / Low stock / Top sellers chips. Sales numbers are **demo**. Inventory KPIs are **Shopify** when credentials work.

### 4. Demo catalog

```
/seed_shopify
  → skip existing titles “IMS Seed — …”
  → create_product() for remaining fixtures
  → best-effort draftOrderCreate + complete (may fail without write_draft_orders)
  → seed local mock analytics if empty
```

Does **not** replace the photo pipeline. Real seller products have no `IMS Seed —` prefix.

## Shopify GraphQL (write path)

`create_product(draft)` in `src/infrastructure/shopify.py`:

1. `productCreate` (title, ACTIVE)
2. `productVariantsBulkUpdate` (price, compare-at)
3. `inventorySetQuantities` at first location
4. Staged upload + `productCreateMedia` if an image file exists

Reads: `list_inventory_products`, `list_seed_products`, optional draft-order mutations.

## Auth and access

- Telegram: optional `TELEGRAM_ALLOWED_USER_ID` (empty = allow anyone who can message the bot).
- Review/dashboard pages: secret token + TTL; no extra login.
- Shopify: cached client-credentials token, or legacy `SHOPIFY_ADMIN_ACCESS_TOKEN`.

## Limits (current)

- Shopify product list is `first: 100` (no pagination).
- Dashboard sales are local mocks, not Shopify Orders API.
- Product create does not set description, SKU, or vendor.
- Local only unless `APP_PUBLIC_URL` is a public host (ngrok, deploy).
