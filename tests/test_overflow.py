import pytest

from src.domain.queries import should_overflow


def test_overflow_on_many_rows():
    answer = {"mode": "text", "telegram_text": "ok", "rows": [[i] for i in range(9)]}
    assert should_overflow(answer, "list products") is True


def test_no_overflow_on_small_answer():
    answer = {"mode": "text", "telegram_text": "2 items", "rows": [[1], [2]]}
    assert should_overflow(answer, "how many products") is False


@pytest.mark.asyncio
async def test_handle_question_returns_text_for_small(monkeypatch, session):
    from src.domain import queries

    async def fake_answer(question, rows, source="local"):
        return {"mode": "text", "telegram_text": "You have 2 products."}

    async def fake_rows(s):
        return [{"name": "A"}, {"name": "B"}]

    monkeypatch.setattr(queries, "answer_inventory_question", fake_answer)
    monkeypatch.setattr(queries, "load_inventory_rows", fake_rows)

    result = await queries.handle_question(session, "how many?", 1)
    assert result["mode"] == "text"
    assert "Local drafts: 2 products" in result["text"]
    assert "2 products" in result["text"]


@pytest.mark.asyncio
async def test_handle_question_returns_link_for_large(monkeypatch, session):
    from src.domain import queries

    rows = [{"name": f"Item {i}", "price": 1, "quantity": 1, "decision": "approved"} for i in range(9)]

    async def fake_answer(question, inventory, source="local"):
        return {
            "mode": "link",
            "telegram_text": "full list",
            "title": "All products",
            "columns": ["name"],
            "rows": [[r["name"]] for r in inventory],
        }

    async def fake_rows(s):
        return rows

    monkeypatch.setattr(queries, "answer_inventory_question", fake_answer)
    monkeypatch.setattr(queries, "load_inventory_rows", fake_rows)

    result = await queries.handle_question(session, "list all", 1)
    assert result["mode"] == "link"
    assert "/d/" in result["url"]
    assert result["text"].startswith("Local drafts: 9 products")
