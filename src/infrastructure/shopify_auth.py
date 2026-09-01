import logging
import time

import httpx

from src.core.config import get_settings

logger = logging.getLogger(__name__)

_token: str | None = None
_token_expires_at: float = 0.0


def _shop_subdomain(domain: str) -> str:
    domain = domain.strip().rstrip("/")
    if domain.endswith(".myshopify.com"):
        return domain.removesuffix(".myshopify.com")
    return domain


async def get_access_token() -> str | None:
    """Return a valid Admin API access token (cached) or None if not configured."""
    global _token, _token_expires_at

    settings = get_settings()
    if settings.shopify_admin_access_token:
        return settings.shopify_admin_access_token

    if not settings.shopify_client_id or not settings.shopify_client_secret:
        return None

    if _token and time.time() < _token_expires_at - 60:
        return _token

    shop = _shop_subdomain(settings.shopify_store_domain)
    url = f"https://{shop}.myshopify.com/admin/oauth/access_token"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.shopify_client_id,
                    "client_secret": settings.shopify_client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPError as exc:
        logger.warning("Shopify token request failed: %s", exc)
        return None

    access_token = body.get("access_token")
    if not access_token:
        logger.warning("Shopify token response missing access_token")
        return None

    _token = access_token
    _token_expires_at = time.time() + float(body.get("expires_in", 86399))
    return _token


def clear_token_cache() -> None:
    global _token, _token_expires_at
    _token = None
    _token_expires_at = 0.0
