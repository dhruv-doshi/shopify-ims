# Shopify IMS

Telegram-first inventory management with product-shot generation and swipe review links.

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
- `APP_PUBLIC_URL` — public URL for review links (use [ngrok](https://ngrok.com/) locally)
- Optional Shopify Partner dev store: `SHOPIFY_STORE_DOMAIN`, `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`

Approved products are pushed to Shopify on **Finish review** (name, price, discount, quantity, and product image). Use `/sync` in Telegram to retry items that failed or were approved before Shopify was configured.

## Run

```bash
source .venv/bin/activate
python -m src.main
```

Health check: `GET http://127.0.0.1:8000/health`

Without `TELEGRAM_BOT_TOKEN`, the web API still runs for local UI testing.

## Shopify (developer mode)

1. Create a free [Shopify Partner](https://partners.shopify.com/) account.
2. Create a development store from the [Dev Dashboard](https://dev.shopify.com/dashboard) (Dev stores sidebar).
3. Create an app in the Dev Dashboard with scopes: `write_products`, `read_products`, `write_inventory`.
4. Install the app on your dev store.
5. In the app **Settings**, copy **Client ID** and **Client secret** into `.env`.

The app exchanges those credentials for a short-lived access token automatically (Shopify client credentials grant). You do not paste a static `shpat_` token unless you have one from a legacy custom app.

Products are created with title, price, compare-at (discount), inventory quantity, and the generated product image.

Optional scopes for demo orders via `/seed_shopify`: `write_draft_orders` and `read_orders`.

## Dashboard and demo catalog

- `/dashboard [question]` — builds a read-only analytics page from **local** mock inventory and sales (`MockProduct` / `MockSale`). Does not write to Shopify. Subtitle labels this as demo analytics.
- `/seed_shopify` — creates real products on your dev store titled `IMS Seed — …` using the same `create_product()` path as review finish. Idempotent (skips existing titles). Best-effort demo draft orders if scopes allow.

## Tests

```bash
pytest
```
