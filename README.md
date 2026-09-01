# Shopify IMS

Telegram-first inventory management: send product photos, review generated shots, push approved items to Shopify, then ask inventory questions or open a short-lived analytics dashboard.

See [TECH.md](TECH.md) for stack, tables, APIs, and data flow.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Fill in `.env`:

- `TELEGRAM_BOT_TOKEN` — from [@BotFather](https://t.me/BotFather)
- `OPENROUTER_API_KEY` — from [OpenRouter](https://openrouter.ai/)
- `APP_PUBLIC_URL` — public URL for review/dashboard links (use [ngrok](https://ngrok.com/) locally)
- Optional Shopify Partner dev store: `SHOPIFY_STORE_DOMAIN`, `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`

## Run

```bash
source .venv/bin/activate
python -m src.main
```

Health check: `GET http://127.0.0.1:8000/health`

Without `TELEGRAM_BOT_TOKEN`, the web API still runs for local UI testing.

## Telegram commands

| Command | What it does |
|---|---|
| Photos | After a short pause, builds a review link `/r/{token}` |
| Text questions | Answers from **live Shopify** inventory when Shopify is configured |
| `/sync` | Pushes approved local drafts that never made it to Shopify |
| `/dashboard [prompt]` | Short-lived page: **live Shopify inventory KPIs** + **demo sales charts** |
| `/seed_shopify` | Writes real `IMS Seed — …` products to the store (optional demo orders) |
| `/status` | Shopify OK, product count, unsent drafts, last batch |

The bot registers these in the Telegram command menu on startup.

## Shopify (developer mode)

1. Create a free [Shopify Partner](https://partners.shopify.com/) account.
2. Create a development store from the [Dev Dashboard](https://dev.shopify.com/dashboard).
3. Create an app with scopes: `write_products`, `read_products`, `write_inventory`.
4. Install the app on your dev store.
5. Copy **Client ID** and **Client secret** into `.env`.

The app uses the Shopify client credentials grant. Optional extra scopes for `/seed_shopify` orders: `write_draft_orders`, `read_orders`.

Approved products are created with title, price, compare-at (discount), inventory quantity, and product image.

## Data sources (important)

| Feature | Inventory | Sales / charts |
|---|---|---|
| Photo → review → Finish | Local drafts, then **write** to Shopify | — |
| Text Q&A | **Shopify** (falls back to local drafts if Shopify is not configured) | — |
| `/dashboard` | **Shopify** when configured, else local mock catalog | **Always local demo sales** (`MockSale`) |
| `/seed_shopify` | **Writes** to Shopify | Also seeds local mock analytics if empty |

## Tests

```bash
pytest
```
