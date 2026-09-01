import base64
import json
import logging
import re
from typing import Any

import httpx

from src.core.config import get_settings

logger = logging.getLogger(__name__)

FALLBACK = {
    "name": "Untitled product",
    "price_options": [9.99, 19.99, 29.99],
    "discount_options": [0, 10, 20],
    "quantity_options": [1, 5, 10],
}


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return json.loads(text)


def _normalize(data: dict[str, Any]) -> dict[str, Any]:
    name = str(data.get("name") or FALLBACK["name"])
    price_options = [float(x) for x in data.get("price_options") or FALLBACK["price_options"]]
    discount_options = [int(x) for x in data.get("discount_options") or FALLBACK["discount_options"]]
    quantity_options = [int(x) for x in data.get("quantity_options") or FALLBACK["quantity_options"]]
    return {
        "name": name,
        "price_options": price_options[:4] or FALLBACK["price_options"],
        "discount_options": discount_options[:4] or FALLBACK["discount_options"],
        "quantity_options": quantity_options[:4] or FALLBACK["quantity_options"],
    }


async def analyze_product_image(image_bytes: bytes, mime: str = "image/jpeg") -> dict[str, Any]:
    settings = get_settings()
    if not settings.openrouter_api_key:
        return dict(FALLBACK)

    b64 = base64.b64encode(image_bytes).decode()
    payload = {
        "model": settings.openrouter_vision_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Analyze this product photo for ecommerce inventory. "
                            "Return ONLY valid JSON with keys: name (string), "
                            "price_options (3-4 numbers), discount_options (3-4 integers percent), "
                            "quantity_options (3-4 integers)."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    },
                ],
            }
        ],
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            json=payload,
            headers=headers,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    try:
        return _normalize(_extract_json(content))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        logger.warning("Vision JSON parse failed; using fallback")
        return dict(FALLBACK)


async def answer_inventory_question(question: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    settings = get_settings()
    if not settings.openrouter_api_key:
        return {"mode": "text", "telegram_text": "No inventory data available yet."}

    payload = {
        "model": settings.openrouter_vision_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You answer seller inventory questions. Return ONLY JSON with keys: "
                    "mode ('text' or 'link'), telegram_text, title, columns (array), "
                    "rows (array of arrays), chart ({labels:[], values:[]}). "
                    "Use mode=link for large tables or chart requests."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({"question": question, "inventory": rows}),
            },
        ],
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            json=payload,
            headers=headers,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    try:
        return _extract_json(content)
    except (json.JSONDecodeError, KeyError, TypeError):
        return {"mode": "text", "telegram_text": "Could not answer that question."}
