import logging
from pathlib import Path

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from src.bot.batching import PendingPhoto, PhotoBatcher
from src.core.config import get_settings
from src.domain.batches import PhotoInput, create_batch, process_batch
from src.domain.dashboard import create_dashboard
from src.domain.inventory import sync_unsent_products
from src.domain.queries import handle_question
from src.domain.shopify_seed import seed_shopify_catalog
from src.infrastructure.database import async_session_factory

logger = logging.getLogger(__name__)

_bot_app: Application | None = None
_batcher: PhotoBatcher | None = None


async def _flush_batch(user_id: int, chat_id: int, photos: list[PendingPhoto]) -> None:
    settings = get_settings()
    async with async_session_factory() as session:
        batch = await create_batch(session, user_id, chat_id)
        await session.commit()
        batch_id = batch.id

    from telegram import Bot

    bot = _bot_app.bot if _bot_app else None
    if bot:
        await bot.send_message(chat_id, f"Processing {len(photos)} photos…")

    async with async_session_factory() as session:
        try:
            token = await process_batch(
                session,
                batch_id,
                [PhotoInput(bytes=p.bytes, mime=p.mime, filename=p.filename) for p in photos],
            )
            url = f"{settings.app_public_url}/r/{token}"
            msg = f"Review your products: {url}"
            if "localhost" in settings.app_public_url or "127.0.0.1" in settings.app_public_url:
                msg += "\n\nNote: use a public URL (e.g. ngrok) to open this on your phone."
            if bot:
                await bot.send_message(chat_id, msg)
        except Exception:
            logger.exception("Batch processing failed")
            if bot:
                await bot.send_message(chat_id, "Failed to process photos. Please try again.")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    settings = get_settings()
    if not settings.is_user_allowed(update.effective_user.id):
        return
    await update.message.reply_text(
        "Send product photos (one or many). After a short pause I'll create a review link. "
        "Ask questions in text to query your inventory.\n"
        "/sync — push approved items to Shopify that haven't been uploaded yet.\n"
        "/dashboard [question] — read-only analytics page (local demo sales).\n"
        "/seed_shopify — create demo products (and orders if allowed) on the Shopify store."
    )


async def sync_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    settings = get_settings()
    if not settings.is_user_allowed(update.effective_user.id):
        return
    if not settings.shopify_configured:
        await update.message.reply_text("Shopify is not configured in .env")
        return
    async with async_session_factory() as session:
        result = await sync_unsent_products(session)
    await update.message.reply_text(
        f"Sync done. Total: {result['total']}, created: {result['ok']}, "
        f"errors: {result['errors']}, skipped: {result['skipped']}"
    )


async def dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    settings = get_settings()
    if not settings.is_user_allowed(update.effective_user.id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    prompt = " ".join(context.args).strip() if context.args else "overview"
    await update.message.reply_text("Building dashboard… (this can take ~15 seconds)")
    try:
        async with async_session_factory() as session:
            result = await create_dashboard(session, prompt, update.effective_chat.id)
        msg = f"{result['telegram_summary']}\n\n{result['url']}"
        if "localhost" in settings.app_public_url or "127.0.0.1" in settings.app_public_url:
            msg += "\n\nNote: use a public URL (e.g. ngrok) to open this on your phone."
        await update.message.reply_text(msg)
    except Exception:
        logger.exception("Dashboard command failed")
        await update.message.reply_text("Dashboard failed. Check server logs and try again.")


async def seed_shopify_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    settings = get_settings()
    if not settings.is_user_allowed(update.effective_user.id):
        return
    if not settings.shopify_configured:
        await update.message.reply_text("Shopify is not configured in .env")
        return
    await update.message.reply_text(
        "Seeding Shopify dev store with demo products (IMS Seed — …). This writes real products."
    )
    async with async_session_factory() as session:
        result = await seed_shopify_catalog(session)
    lines = [
        f"Products created: {result['products_created']}",
        f"Products skipped: {result['products_skipped']}",
        f"Orders created: {result['orders_created']}",
        f"Orders skipped: {result['orders_skipped']}",
    ]
    if result["errors"]:
        lines.append("Errors: " + "; ".join(result["errors"][:3]))
    await update.message.reply_text("\n".join(lines))


def get_bot():
    return _bot_app.bot if _bot_app else None


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message or not _batcher:
        return
    settings = get_settings()
    if not settings.is_user_allowed(update.effective_user.id):
        return

    if update.message.photo:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        data = await file.download_as_bytearray()
        pending = PendingPhoto(bytes=bytes(data), mime="image/jpeg", filename="photo.jpg")
    elif update.message.document and (update.message.document.mime_type or "").startswith("image/"):
        doc = update.message.document
        file = await doc.get_file()
        data = await file.download_as_bytearray()
        mime = doc.mime_type or "image/jpeg"
        pending = PendingPhoto(
            bytes=bytes(data),
            mime=mime,
            filename=doc.file_name or f"photo{Path(doc.file_name or '').suffix or '.jpg'}",
        )
    else:
        return

    _batcher.add(update.effective_chat.id, update.effective_user.id, pending)


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message or not update.message.text:
        return
    settings = get_settings()
    if not settings.is_user_allowed(update.effective_user.id):
        return

    async with async_session_factory() as session:
        result = await handle_question(session, update.message.text, update.effective_chat.id)

    if result["mode"] == "link":
        await update.message.reply_text(f"Report ready: {result['url']}")
    else:
        await update.message.reply_text(result["text"])


def build_bot_application() -> Application | None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN not set; bot polling disabled")
        return None

    global _bot_app, _batcher
    app = Application.builder().token(settings.telegram_bot_token).build()
    _bot_app = app
    _batcher = PhotoBatcher(on_flush=_flush_batch)

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("sync", sync_command))
    app.add_handler(CommandHandler("dashboard", dashboard_command))
    app.add_handler(CommandHandler("seed_shopify", seed_shopify_command))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.Document.IMAGE, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    return app
