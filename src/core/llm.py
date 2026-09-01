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


async def answer_inventory_question(
    question: str, rows: list[dict[str, Any]], source: str = "local"
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.openrouter_api_key:
        count = len(rows)
        return {"mode": "text", "telegram_text": f"You have {count} products."}

    source_note = (
        "Inventory rows are live products from the connected Shopify store."
        if source == "shopify"
        else "Inventory rows are local draft records from this app (not live Shopify)."
    )
    payload = {
        "model": settings.openrouter_vision_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You answer seller inventory questions. Return ONLY JSON with keys: "
                    "mode ('text' or 'link'), telegram_text, title, columns (array), "
                    "rows (array of arrays), chart ({labels:[], values:[]}). "
                    "Use mode=link for large tables or chart requests. "
                    f"{source_note}"
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


def _cap_dashboard_spec(spec: dict[str, Any], prompt: str) -> dict[str, Any]:
    raw_kpis = spec.get("kpis")
    if isinstance(raw_kpis, dict):
        kpis = [{"label": str(k), "value": str(v), "hint": ""} for k, v in raw_kpis.items()]
    elif isinstance(raw_kpis, list):
        kpis = list(raw_kpis)
    else:
        kpis = []
    kpis = kpis[:6]
    charts = list(spec.get("charts") or [])[:3]
    tables = list(spec.get("tables") or [])[:2]
    for chart in charts:
        labels = list(chart.get("labels") or [])[:12]
        values = list(chart.get("values") or [])[:12]
        chart["labels"] = labels
        chart["values"] = values[: len(labels)]
        if chart.get("values_b") is not None:
            chart["values_b"] = list(chart.get("values_b") or [])[: len(labels)]
    for table in tables:
        table["rows"] = list(table.get("rows") or [])[:15]
    summary = str(spec.get("telegram_summary") or "")[:500]
    return {
        "title": str(spec.get("title") or "Inventory dashboard"),
        "subtitle": str(spec.get("subtitle") or "Demo analytics — local mock sales"),
        "prompt": prompt,
        "telegram_summary": summary,
        "kpis": kpis,
        "charts": charts,
        "tables": tables,
    }


def fallback_dashboard_spec(prompt: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    kpis_data = snapshot.get("kpis") or {}
    sales_by_day = list(snapshot.get("sales_by_day") or [])[-7:]
    sales_by_product = list(snapshot.get("sales_by_product") or [])[:10]

    kpis = [
        {"label": "Units on hand", "value": str(kpis_data.get("units_on_hand", 0)), "hint": ""},
        {"label": "Inventory value", "value": f"${kpis_data.get('inventory_value', 0):,.2f}", "hint": ""},
        {"label": "Revenue (30d)", "value": f"${kpis_data.get('revenue_30d', 0):,.2f}", "hint": "Demo analytics"},
        {"label": "Units sold (30d)", "value": str(kpis_data.get("units_sold_30d", 0)), "hint": ""},
    ]

    charts = []
    if sales_by_day:
        charts.append(
            {
                "type": "bar",
                "title": "Revenue — last 7 days",
                "labels": [d["day"][5:] for d in sales_by_day],
                "values": [round(d["revenue"], 2) for d in sales_by_day],
                "values_b": None,
            }
        )

    tables = []
    if sales_by_product:
        tables.append(
            {
                "title": "Top products (30d)",
                "columns": ["Product", "Units", "Revenue"],
                "rows": [
                    [p["name"], str(p["units"]), f"${p['revenue']:,.2f}"] for p in sales_by_product[:10]
                ],
            }
        )

    low_stock = [p for p in snapshot.get("inventory") or [] if p.get("qty", 0) <= 5]
    if prompt and "low" in prompt.lower() and low_stock:
        tables.append(
            {
                "title": "Low stock",
                "columns": ["Product", "Qty", "Price"],
                "rows": [[p["name"], str(p["qty"]), f"${p['price']:.2f}"] for p in low_stock[:10]],
            }
        )

    summary = (
        f"Demo analytics for “{prompt}”. "
        f"{kpis_data.get('units_on_hand', 0)} units on hand; "
        f"${kpis_data.get('revenue_30d', 0):,.2f} revenue (30d)."
    )
    return _cap_dashboard_spec(
        {
            "title": "Inventory dashboard",
            "subtitle": "Demo analytics — local mock sales (not Shopify orders)",
            "telegram_summary": summary[:500],
            "kpis": kpis,
            "charts": charts,
            "tables": tables,
        },
        prompt,
    )


async def build_dashboard_spec(prompt: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    if not settings.openrouter_api_key:
        return fallback_dashboard_spec(prompt, snapshot)

    payload = {
        "model": settings.openrouter_vision_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Build a read-only seller dashboard spec from inventory snapshot JSON. "
                    "Return ONLY JSON with keys: title, subtitle (mention Demo analytics), "
                    "telegram_summary (max 500 chars), kpis (array of {label,value,hint}), "
                    "charts (array of {type: bar|line, title, labels, values, values_b}), "
                    "tables (array of {title, columns, rows}). "
                    "Max 6 KPIs, 3 charts, 2 tables, 12 chart labels, 15 table rows. "
                    "Widgets must reflect the user prompt."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({"prompt": prompt, "snapshot": snapshot}),
            },
        ],
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{settings.openrouter_base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        spec = _extract_json(content)
        return _cap_dashboard_spec(spec, prompt)
    except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        logger.warning("Dashboard spec LLM failed; using fallback")
        return fallback_dashboard_spec(prompt, snapshot)
