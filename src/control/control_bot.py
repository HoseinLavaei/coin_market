"""
Control bot – runs the subscription flow.
"""

import sys

import logger

from typing import Any

from telegram import Bot
from telegram.ext import ApplicationBuilder, Application, CallbackContext, JobQueue

from .menus import control_conversation
from ..db.init_db import init_db
from ..environment import CONTROL_BOT_TOKEN


async def run_control_bot() -> Application[
    Bot, CallbackContext[Any, Any, Any, Any], Any, Any, Any, JobQueue[Any] | None]:
    """Run the control bot with the conversation handler."""
    if not CONTROL_BOT_TOKEN:
        logger.error("Error: CONTROL_BOT_TOKEN environment variable not set.")
        sys.exit(1)

    logger.info("Initializing database...")
    await init_db()

    app = ApplicationBuilder().token(CONTROL_BOT_TOKEN).build()
    app.add_handler(control_conversation)

    logger.info("Control bot started.")

    return app
