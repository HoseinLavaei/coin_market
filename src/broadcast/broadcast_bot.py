"""
Broadcast bot – handles /start KEY activation and stores the bot instance.
"""

import sys
from typing import Any

from telegram import Bot
from telegram.ext import ApplicationBuilder, CommandHandler, Application, CallbackContext, JobQueue

from .handlers import handle_start
from ..db.init_db import init_db
from ..environment import BROADCAST_BOT_TOKEN


async def run_broadcast_bot() -> Application[
    Bot, CallbackContext[Any, Any, Any, Any], Any, Any, Any, JobQueue[Any] | None]:
    """Run the broadcast bot."""
    if not BROADCAST_BOT_TOKEN:
        print("Error: BROADCAST_BOT_TOKEN environment variable not set.")
        sys.exit(1)

    print("Initializing database...")
    await init_db()

    app = ApplicationBuilder().token(BROADCAST_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", handle_start))

    print("Broadcast bot started.")
    print("Use /start KEY to activate a subscription.")

    return app
