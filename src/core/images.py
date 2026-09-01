import base64
import logging
from pathlib import Path

import httpx

from src.core.config import get_settings
from src.core.image_io import decode_image_b64, write_image

logger = logging.getLogger(__name__)

PROMPT = (
    "Professional ecommerce product photograph of this exact item. "
    "Seamless studio background, even lighting, no props, no text, no people, "
    "no clutter. Centered, sharp, catalog style."
)


async def generate_product_shot(image_bytes: bytes, output_path: Path, mime: str = "image/jpeg") -> Path | None:
    settings = get_settings()
    if not settings.openrouter_api_key:
        return None

    b64 = base64.b64encode(image_bytes).decode()
    payload = {
        "model": settings.openrouter_image_model,
        "prompt": PROMPT,
        "input_references": [
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
        ],
        "aspect_ratio": "1:1",
    }
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(
                f"{settings.openrouter_base_url}/images",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json().get("data") or []
            if not data or not data[0].get("b64_json"):
                return None
            raw = decode_image_b64(data[0]["b64_json"])
            return write_image(output_path, raw)
    except (httpx.HTTPError, KeyError, ValueError, OSError) as exc:
        logger.warning("Image generation failed: %s", exc)
        return None
