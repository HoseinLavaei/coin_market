"""
Control bot – runs the subscription flow.
"""

import sys

from telegram.ext import Application, ApplicationBuilder
from telegram.request import HTTPXRequest

from src import logger
from .menus import control_conversation
from ..db.init_db import init_db
from ..environment import CONTROL_BOT_TOKEN


async def run_control_bot() -> Application:
    """Run the control bot with the conversation handler."""
    if not CONTROL_BOT_TOKEN:
        logger.error("Error: CONTROL_BOT_TOKEN environment variable not set.")
        sys.exit(1)

    logger.info("Initializing database...")
    await init_db()

    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0,
    )

    app = ApplicationBuilder().token(CONTROL_BOT_TOKEN).request(request).build()
    app.add_handler(control_conversation)

    logger.info("Control bot started.")

    return app
