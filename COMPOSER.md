# Composer handoff — Telegram Shopify IMS (v1)

You are implementing this repo from an empty tree except [`base_idea.txt`](base_idea.txt) and this file. Do not re-open architecture. Do not add a second app, Next.js, Celery, Redis, Postgres, Docker, Nginx, pi-agent, or Shopify OAuth.

Follow Karpathy: minimum code, no speculative features, every step has a verify check.

## Locked decisions (do not change)

| Topic | Decision |
|---|---|
| Shape | **One FastAPI process**: bot + APIs + review/data HTML |
| DB | SQLite via SQLAlchemy 2 async + aiosqlite |
| Telegram | **Polling** (not webhook) in FastAPI lifespan |
| Links | Unguessable UUID in URL is the only auth; default TTL 24h |
| Review UI | **Carousel** (not Tinder stack). Still **record** pointer swipe left/right |
| Approve | Swipe right = approve generated image. Left = reject. Rejected items never go to Shopify |
| Autofill | Vision model: `name` + pick-lists for price, discount %, quantity (3–4 options each) + custom override |
| LLM | OpenRouter only. Chat for vision/JSON/NL. `POST /api/v1/images` for product shots |
| Shopify | Custom app on a **Partner development store**. Admin **GraphQL**. If token missing: local save, `shopify_status=skipped` |
| Users | `TELEGRAM_ALLOWED_USER_ID` empty = allow anyone (solo test); if set, ignore other users |
| Discount | Stored as percent. Shopify `compareAtPrice` = price / (1 - discount/100) when discount > 0, else omit compare-at |

Human setup (you do not create these): Telegram bot token, OpenRouter key, optional ngrok `APP_PUBLIC_URL`, optional Shopify Partner store + custom app token.

## Repo layout (create exactly this)

```
shopify-ims/
  COMPOSER.md                 # this file — do not expand with essays
  base_idea.txt               # do not rewrite
  README.md                   # run instructions only
  pyproject.toml
  .env.example
  .gitignore                  # .env, data/, __pycache__, .venv
  src/
    __init__.py
    main.py                   # app factory, mount static, include routers, start bot
    core/
      config.py
      llm.py                  # OpenRouter chat completions
      images.py               # OpenRouter /images
    infrastructure/
      database.py             # engine, session, create_all on startup
      models.py               # ORM
      shopify.py              # GraphQL client; no-op if no token
    domain/
      batches.py              # photo ingest, debounce, process item
      review.py               # session + swipe + finalize
      queries.py              # NL Q → telegram vs data link
    api/
      review.py               # GET page + JSON APIs for carousel
      data.py                 # GET data page + JSON
      media.py                # GET uploaded images (token-gated)
    bot/
      app.py                  # Application + handlers
      batching.py             # per-chat debounce
    web/
      templates/
        review.html
        data.html
      static/
        review.js
        review.css
        data.js
        data.css
  tests/
    conftest.py
    test_links.py
    test_swipe.py
    test_overflow.py
    test_shopify_skip.py
  data/                       # gitignored; created at runtime
```

Python package: `src` on `PYTHONPATH` or `pyproject` with `packages = [{include = "src"}]` — pick one and make `python -m src.main` work.

## Data model

`ShortLink`: `id`, `token` (uuid str unique), `kind` (`review` | `data`), `expires_at`, `payload_json` (for data pages), `telegram_chat_id`, `created_at`.

`Batch`: `id`, `telegram_user_id`, `telegram_chat_id`, `status` (`collecting` | `processing` | `ready` | `failed`), `review_link_id` FK nullable.

`ProductDraft`: `id`, `batch_id`, `original_path`, `generated_path` nullable, `generation_failed` bool, `name`, `price` (numeric string or Decimal), `discount_percent`, `quantity` int, `price_options_json`, `discount_options_json`, `quantity_options_json`, `decision` (`pending` | `approved` | `rejected`), `shopify_status` (`unsent` | `skipped` | `ok` | `error`), `shopify_product_id` nullable, `shopify_error` nullable.

`SwipeEvent`: `id`, `product_id`, `direction` (`left` | `right`), `dx`, `dy`, `client_ts` optional, `created_at`. Persist **every** swipe, including repeats; last swipe on a card sets `decision`.

Startup: `create_all`. No Alembic in v1.

## Config (`.env.example`)

```
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_USER_ID=
OPENROUTER_API_KEY=
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_VISION_MODEL=google/gemini-2.5-flash
OPENROUTER_IMAGE_MODEL=google/gemini-2.5-flash-image
APP_PUBLIC_URL=http://127.0.0.1:8000
LINK_TTL_HOURS=24
PHOTO_BATCH_IDLE_SECONDS=3
IMAGE_CONCURRENCY=3
SHOPIFY_STORE_DOMAIN=
SHOPIFY_ADMIN_ACCESS_TOKEN=
SHOPIFY_API_VERSION=2025-01
DATABASE_URL=sqlite+aiosqlite:///./data/app.db
```

Never log tokens or API keys.

## OpenRouter

**Vision** (`src/core/llm.py`): `POST /chat/completions`, image as `data:image/jpeg;base64,...`. Force JSON. Schema:

```json
{
  "name": "string",
  "price_options": [9.99, 14.99, 19.99],
  "discount_options": [0, 10, 20],
  "quantity_options": [1, 5, 10]
}
```

Set draft `name` to first name; set current price/discount/quantity to **first option**. If parse fails: name `"Untitled product"`, fallback options `[9.99,19.99,29.99]`, `[0,10,20]`, `[1,5,10]`.

**Image** (`src/core/images.py`): `POST {OPENROUTER_BASE_URL}/images` (same host, path `/images` not `/chat/completions`).

```json
{
  "model": "<OPENROUTER_IMAGE_MODEL>",
  "prompt": "Professional ecommerce product photograph of this exact item. Seamless studio background, even lighting, no props, no text, no people, no clutter. Centered, sharp, catalog style.",
  "input_references": [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}],
  "aspect_ratio": "1:1"
}
```

Read `data[0].b64_json`. Write JPEG/PNG under `data/uploads/{batch_id}/`. On HTTP/parse error: `generation_failed=true`, `generated_path=original_path`.

## Telegram

- `/start` → one-line how to send photos and ask questions.
- Photos (and photo documents): save bytes, add to per-chat buffer. After `PHOTO_BATCH_IDLE_SECONDS` with no new photo, freeze batch, reply “Processing N photos…”, run pipeline with `IMAGE_CONCURRENCY`, create review `ShortLink`, reply `{APP_PUBLIC_URL}/r/{token}`.
- If `APP_PUBLIC_URL` is localhost, still send the link; mention they need a public URL on a phone.
- Non-photo text → `domain/queries.py`.
- Ignore unauthorized users when `TELEGRAM_ALLOWED_USER_ID` is set.

## HTTP

All JSON errors: `{"detail": "..."}`. Expired/missing token → 404.

| Method | Path | Behavior |
|---|---|---|
| GET | `/r/{token}` | Review HTML if link kind=review and not expired |
| GET | `/api/review/{token}` | `{expires_at, products: [{id, image_url, name, price, discount_percent, quantity, options, decision, generation_failed}]}` |
| PATCH | `/api/review/{token}/products/{id}` | Update name/price/discount/quantity |
| POST | `/api/review/{token}/products/{id}/swipe` | Body `{direction, dx, dy, client_ts?}`. Save SwipeEvent; set decision |
| POST | `/api/review/{token}/finish` | Persist decisions; for approved, call Shopify; Telegram message with counts |
| GET | `/media/{token}/{product_id}` | Serve generated (or original) image; same token as review |
| GET | `/d/{token}` | Data HTML |
| GET | `/api/data/{token}` | Payload for table/chart |

## Review UI

Carousel: one product at a time, generated image, name input, chip rows for price/discount/qty, custom input, prev/next. Pointer: if horizontal movement > 60px, fire swipe API (right=approve, left=reject), then advance. Buttons “Reject” / “Approve” do the same. Record swipe even when using buttons (`dx/dy` 0). Finish button on last card or always visible. Do not require Shopify to use the page.

## Queries / overflow

Load local drafts + approved inventory (keep it simple: query `ProductDraft` where decision=approved, plus pending in recent batches). Send a compact table to the vision/text model: question + rows. Model returns JSON:

```json
{"mode": "text"|"link", "telegram_text": "...", "title": "...", "columns": ["..."], "rows": [[...]], "chart": {"labels": ["..."], "values": [0]} }
```

`mode=link` when rows > 8 **or** user asks for chart/graph/breakdown **or** telegram_text would exceed 1500 chars. Then store payload on a `data` ShortLink and send `/d/{token}`. Otherwise send `telegram_text` only. Chart on data page: one bar or line using a tiny chart lib or plain CSS bars — no heavy framework.

## Shopify adapter

`create_product(draft) -> {status, product_id, error}`.

If domain or token empty: `skipped`.

Else Admin GraphQL `https://{SHOPIFY_STORE_DOMAIN}/admin/api/{SHOPIFY_API_VERSION}/graphql.json` with `X-Shopify-Access-Token`.

Create product with title, one variant (price, inventory), optional `compareAtPrice`, image from generated file (Shopify staged upload **or** `productCreate` with image url if you host it — for v1, `productCreate` media using `https` is hard locally). Prefer: `productCreate` with title + variant; then `productCreateMedia` with `originalSource` as a data URL **only if API allows**; otherwise skip image upload in v1 and still create the product (document in README). Do not block the whole finish flow on image upload failure.

Scopes expected: `write_products`, `read_products`, `write_inventory`.

## Implementation order (loop each until verify)

1. Scaffold pyproject, config, DB, empty FastAPI, `GET /health` → `uvicorn` serves health.
2. Models + link helper `create_link(kind, ttl)` / `get_valid_link(token)` → tests in `test_links.py` (valid, expired, wrong kind).
3. OpenRouter wrappers with httpx; unit tests mock httpx (no live key required in CI).
4. Batch pipeline: fake vision/image in tests; writes files + ProductDrafts + review link.
5. Telegram batching debounce: unit-test the buffer (fake clock / short idle), not a live bot.
6. Review APIs + HTML/JS. `test_swipe.py`: swipe persists, left/right sets decision, finish without Shopify token → `skipped`.
7. Shopify client: `test_shopify_skip.py` empty token; one mocked GraphQL success test.
8. Queries + overflow: `test_overflow.py` 9 rows → link; 2 rows → text.
9. README: `.env`, `python -m venv`, install, `python -m src.main`, ngrok note, Partner store note.

## Tests

pytest + httpx `AsyncClient` + pytest-asyncio. No live OpenRouter/Telegram/Shopify in tests. Mock those clients.

## Done when

- `pytest` passes.
- `python -m src.main` starts FastAPI + bot polling (bot no-ops if token empty, log a warning, **app still serves** `/r/` for local UI testing).
- Sending N photos (with token) yields one `/r/{token}` after idle.
- Opening that URL shows carousel, chips, swipe events in DB.
- Finish without Shopify token saves locally.
- “List all products” with many rows yields `/d/{token}` with a table.

## Do not

- Rewrite this plan mid-flight unless a locked decision is impossible.
- Add auth, multi-tenant, webhooks, Celery, Docker, Next.js, pi-agent, Shopify embedded app.
- Commit `.env` or `data/`.
- Invent extra product fields (SKU, tags, collections) unless required by the Shopify mutation you use.
