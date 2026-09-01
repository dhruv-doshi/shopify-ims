import logging

logger = logging.getLogger(__name__)


async def send_telegram_message(chat_id: int, text: str) -> None:
    from src.bot.app import get_bot

    bot = get_bot()
    if bot is None:
        logger.warning("Telegram bot not running; message not sent: %s", text[:80])
        return
    await bot.send_message(chat_id=chat_id, text=text)


def format_finish_summary(result: dict) -> str:
    lines = [
        "Review complete.",
        f"Approved: {result.get('approved', 0)}",
        f"Rejected: {result.get('rejected', 0)}",
        f"Shopify created: {result.get('shopify_ok', 0)}",
    ]
    if result.get("shopify_skipped"):
        lines.append(f"Shopify skipped: {result['shopify_skipped']}")
    if result.get("shopify_errors"):
        lines.append(f"Shopify errors: {result['shopify_errors']}")
    if result.get("shopify_ok", 0) > 0:
        lines.append("Check Products in your Shopify admin.")
    lines.append("Review link is now closed.")
    return "\n".join(lines)
