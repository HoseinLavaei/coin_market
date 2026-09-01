"""
Broadcast bot – handles /start KEY activation and stores the bot instance.
"""

import sys

from telegram.ext import Application, ApplicationBuilder, CommandHandler
from telegram.request import HTTPXRequest

from src import logger
from .handlers import handle_start
from ..db.init_db import init_db
from ..environment import BROADCAST_BOT_TOKEN


async def run_broadcast_bot() -> Application:
    """Run the broadcast bot."""
    if not BROADCAST_BOT_TOKEN:
        logger.error("Error: BROADCAST_BOT_TOKEN environment variable not set.")
        sys.exit(1)

    await init_db()

    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0,
    )

    app = ApplicationBuilder().token(BROADCAST_BOT_TOKEN).request(request).build()
    app.add_handler(CommandHandler("start", handle_start))

    logger.info("Broadcast bot started.")

    return app
