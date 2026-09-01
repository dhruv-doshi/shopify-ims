import logging
from decimal import Decimal
from pathlib import Path

import httpx

from src.core.config import get_settings
from src.core.image_io import image_extension
from src.infrastructure.models import ProductDraft
from src.infrastructure.shopify_auth import get_access_token

logger = logging.getLogger(__name__)

CREATE_PRODUCT = """
mutation productCreate($product: ProductCreateInput!) {
  productCreate(product: $product) {
    product {
      id
      title
      variants(first: 1) {
        nodes {
          id
          inventoryItem { id }
        }
      }
    }
    userErrors { field message }
  }
}
"""

UPDATE_VARIANTS = """
mutation productVariantsBulkUpdate($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
  productVariantsBulkUpdate(productId: $productId, variants: $variants) {
    productVariants { id price }
    userErrors { field message }
  }
}
"""

SET_INVENTORY = """
mutation inventorySetQuantities($input: InventorySetQuantitiesInput!) {
  inventorySetQuantities(input: $input) {
    userErrors { field message }
  }
}
"""

STAGED_UPLOAD = """
mutation stagedUploadsCreate($input: [StagedUploadInput!]!) {
  stagedUploadsCreate(input: $input) {
    stagedTargets {
      url
      resourceUrl
      parameters { name value }
    }
    userErrors { field message }
  }
}
"""

CREATE_MEDIA = """
mutation productCreateMedia($productId: ID!, $media: [CreateMediaInput!]!) {
  productCreateMedia(productId: $productId, media: $media) {
    media { id status }
    mediaUserErrors { field message }
  }
}
"""

GET_LOCATION = """
{
  locations(first: 1) {
    edges { node { id } }
  }
}
"""


def _compare_at(price: Decimal, discount_percent: int) -> str | None:
    if discount_percent <= 0:
        return None
    factor = Decimal("1") - (Decimal(discount_percent) / Decimal("100"))
    if factor <= 0:
        return None
    return str((price / factor).quantize(Decimal("0.01")))


def _product_image_path(draft: ProductDraft) -> Path | None:
    path_str = draft.generated_path or draft.original_path
    if not path_str:
        return None
    path = Path(path_str)
    return path if path.exists() else None


def _mime_for_path(path: Path) -> str:
    ext = image_extension(path.read_bytes()) if path.exists() else path.suffix
    if ext == ".png":
        return "image/png"
    if ext == ".webp":
        return "image/webp"
    return "image/jpeg"


async def _graphql(client: httpx.AsyncClient, query: str, variables: dict | None = None) -> dict:
    settings = get_settings()
    token = await get_access_token()
    if not token:
        raise RuntimeError("Could not obtain Shopify access token")
    url = f"https://{settings.shopify_store_domain}/admin/api/{settings.shopify_api_version}/graphql.json"
    response = await client.post(
        url,
        json={"query": query, "variables": variables or {}},
        headers={
            "X-Shopify-Access-Token": token,
            "Content-Type": "application/json",
        },
    )
    response.raise_for_status()
    body = response.json()
    if body.get("errors"):
        msg = "; ".join(e.get("message", "unknown") for e in body["errors"])
        raise RuntimeError(msg)
    return body


def _user_errors(payload: dict | None, error_key: str = "userErrors") -> str | None:
    if not payload:
        return "No response payload"
    errors = payload.get(error_key) or payload.get("userErrors") or []
    if errors:
        return "; ".join(e.get("message", "unknown") for e in errors)
    return None


async def _upload_product_image(client: httpx.AsyncClient, product_id: str, image_path: Path) -> str | None:
    mime = _mime_for_path(image_path)
    filename = image_path.name
    staged_body = await _graphql(
        client,
        STAGED_UPLOAD,
        {
            "input": [
                {
                    "filename": filename,
                    "mimeType": mime,
                    "resource": "PRODUCT_IMAGE",
                    "httpMethod": "POST",
                }
            ]
        },
    )
    staged_payload = staged_body.get("data", {}).get("stagedUploadsCreate")
    err = _user_errors(staged_payload)
    if err:
        logger.warning("Shopify staged upload failed: %s", err)
        return err
    targets = (staged_payload or {}).get("stagedTargets") or []
    if not targets:
        return "No staged upload target"
    target = targets[0]
    form = {p["name"]: p["value"] for p in target["parameters"]}
    image_bytes = image_path.read_bytes()
    upload = await client.post(
        target["url"],
        data=form,
        files={"file": (filename, image_bytes, mime)},
    )
    if upload.status_code not in (200, 201, 204):
        return f"Image upload HTTP {upload.status_code}"

    media_body = await _graphql(
        client,
        CREATE_MEDIA,
        {
            "productId": product_id,
            "media": [{"originalSource": target["resourceUrl"], "mediaContentType": "IMAGE"}],
        },
    )
    media_payload = media_body.get("data", {}).get("productCreateMedia")
    return _user_errors(media_payload, "mediaUserErrors")


async def create_product(draft: ProductDraft) -> dict:
    settings = get_settings()
    if not settings.shopify_configured:
        return {"status": "skipped", "product_id": None, "error": None}

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            create_body = await _graphql(
                client,
                CREATE_PRODUCT,
                {"product": {"title": draft.name, "status": "ACTIVE"}},
            )
            create_payload = create_body.get("data", {}).get("productCreate")
            err = _user_errors(create_payload)
            product = (create_payload or {}).get("product")
            if err or not product:
                return {"status": "error", "product_id": None, "error": err or "No product returned"}

            variant = product["variants"]["nodes"][0]
            variant_input: dict = {"id": variant["id"], "price": str(draft.price)}
            compare_at = _compare_at(draft.price, draft.discount_percent)
            if compare_at:
                variant_input["compareAtPrice"] = compare_at

            update_body = await _graphql(
                client,
                UPDATE_VARIANTS,
                {"productId": product["id"], "variants": [variant_input]},
            )
            update_payload = update_body.get("data", {}).get("productVariantsBulkUpdate")
            err = _user_errors(update_payload)
            if err:
                return {"status": "error", "product_id": product["id"], "error": err}

            if draft.quantity > 0:
                loc_body = await _graphql(client, GET_LOCATION)
                edges = loc_body.get("data", {}).get("locations", {}).get("edges") or []
                if edges:
                    location_id = edges[0]["node"]["id"]
                    inv_body = await _graphql(
                        client,
                        SET_INVENTORY,
                        {
                            "input": {
                                "name": "available",
                                "reason": "correction",
                                "ignoreCompareQuantity": True,
                                "quantities": [
                                    {
                                        "inventoryItemId": variant["inventoryItem"]["id"],
                                        "locationId": location_id,
                                        "quantity": draft.quantity,
                                    }
                                ],
                            }
                        },
                    )
                    inv_payload = inv_body.get("data", {}).get("inventorySetQuantities")
                    inv_err = _user_errors(inv_payload)
                    if inv_err:
                        logger.warning("Shopify inventory update failed: %s", inv_err)

            image_path = _product_image_path(draft)
            if image_path:
                img_err = await _upload_product_image(client, product["id"], image_path)
                if img_err:
                    logger.warning("Shopify image upload failed for %s: %s", draft.name, img_err)

            return {"status": "ok", "product_id": product["id"], "error": None}
    except (httpx.HTTPError, RuntimeError) as exc:
        logger.warning("Shopify create failed: %s", exc)
        return {"status": "error", "product_id": None, "error": str(exc)}
