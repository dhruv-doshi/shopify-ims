from telegram import BotCommand

BOT_COMMANDS = [
    BotCommand("start", "How to send photos and use commands"),
    BotCommand("sync", "Push unsent approved products to Shopify"),
    BotCommand("dashboard", "Read-only analytics page"),
    BotCommand("seed_shopify", "Create demo products on the Shopify store"),
    BotCommand("status", "Shopify, product count, unsent drafts, last batch"),
]


async def register_bot_commands(application) -> None:
    await application.bot.set_my_commands(BOT_COMMANDS)
