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

LIST_SEED_PRODUCTS = """
query {
  products(first: 50, query: "title:IMS Seed") {
    edges {
      node {
        title
        variants(first: 1) {
          nodes { id }
        }
      }
    }
  }
}
"""

LIST_INVENTORY_PRODUCTS = """
query {
  products(first: 100) {
    edges {
      node {
        id
        title
        status
        variants(first: 10) {
          nodes {
            id
            price
            inventoryQuantity
          }
        }
      }
    }
  }
}
"""

DRAFT_ORDER_CREATE = """
mutation draftOrderCreate($input: DraftOrderInput!) {
  draftOrderCreate(input: $input) {
    draftOrder { id }
    userErrors { field message }
  }
}
"""

DRAFT_ORDER_COMPLETE = """
mutation draftOrderComplete($id: ID!) {
  draftOrderComplete(id: $id) {
    draftOrder { id }
    userErrors { field message }
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
        return {"status": "skipped", "product_id": None, "variant_id": None, "error": None}

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
                return {
                    "status": "error",
                    "product_id": None,
                    "variant_id": None,
                    "error": err or "No product returned",
                }

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
                return {
                    "status": "error",
                    "product_id": product["id"],
                    "variant_id": variant["id"],
                    "error": err,
                }

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

            return {
                "status": "ok",
                "product_id": product["id"],
                "variant_id": variant["id"],
                "error": None,
            }
    except (httpx.HTTPError, RuntimeError) as exc:
        logger.warning("Shopify create failed: %s", exc)
        return {"status": "error", "product_id": None, "variant_id": None, "error": str(exc)}


async def list_inventory_products() -> list[dict]:
    settings = get_settings()
    if not settings.shopify_configured:
        return []
    async with httpx.AsyncClient(timeout=60) as client:
        body = await _graphql(client, LIST_INVENTORY_PRODUCTS)
    edges = body.get("data", {}).get("products", {}).get("edges") or []
    rows = []
    for edge in edges:
        node = edge.get("node") or {}
        variants = (node.get("variants") or {}).get("nodes") or []
        if not variants:
            rows.append(
                {
                    "id": node.get("id"),
                    "name": node.get("title") or "Untitled",
                    "price": 0.0,
                    "discount_percent": 0,
                    "quantity": 0,
                    "decision": (node.get("status") or "unknown").lower(),
                    "shopify_status": "ok",
                    "source": "shopify",
                }
            )
            continue
        total_qty = sum(int(v.get("inventoryQuantity") or 0) for v in variants)
        rows.append(
            {
                "id": node.get("id"),
                "name": node.get("title") or "Untitled",
                "price": float(variants[0].get("price") or 0),
                "discount_percent": 0,
                "quantity": total_qty,
                "decision": (node.get("status") or "unknown").lower(),
                "shopify_status": "ok",
                "source": "shopify",
            }
        )
    return rows


async def list_seed_products() -> list[dict]:
    settings = get_settings()
    if not settings.shopify_configured:
        return []
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            body = await _graphql(client, LIST_SEED_PRODUCTS)
        edges = body.get("data", {}).get("products", {}).get("edges") or []
        out = []
        for edge in edges:
            node = edge.get("node") or {}
            variants = (node.get("variants") or {}).get("nodes") or []
            out.append(
                {
                    "title": node.get("title") or "",
                    "variant_id": variants[0]["id"] if variants else None,
                }
            )
        return out
    except (httpx.HTTPError, RuntimeError) as exc:
        logger.warning("Shopify list seed products failed: %s", exc)
        return []


async def create_demo_orders(variant_ids: list[str], count: int = 4) -> dict:
    if not variant_ids:
        return {"orders_created": 0, "orders_skipped": count, "error": "No variant IDs"}
    settings = get_settings()
    if not settings.shopify_configured:
        return {"orders_created": 0, "orders_skipped": count, "error": "Shopify not configured"}

    created = 0
    skipped = 0
    last_error: str | None = None
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            for i in range(count):
                variant_id = variant_ids[i % len(variant_ids)]
                create_body = await _graphql(
                    client,
                    DRAFT_ORDER_CREATE,
                    {"input": {"lineItems": [{"variantId": variant_id, "quantity": 1}]}},
                )
                create_payload = create_body.get("data", {}).get("draftOrderCreate")
                err = _user_errors(create_payload)
                draft = (create_payload or {}).get("draftOrder")
                if err or not draft:
                    skipped += count - i
                    last_error = err or "draftOrderCreate failed"
                    break
                complete_body = await _graphql(
                    client,
                    DRAFT_ORDER_COMPLETE,
                    {"id": draft["id"]},
                )
                complete_payload = complete_body.get("data", {}).get("draftOrderComplete")
                err = _user_errors(complete_payload)
                if err:
                    skipped += count - i
                    last_error = err
                    break
                created += 1
    except (httpx.HTTPError, RuntimeError) as exc:
        skipped = count - created
        last_error = str(exc)

    return {
        "orders_created": created,
        "orders_skipped": skipped,
        "error": last_error,
    }
