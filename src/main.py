"""
Main entry point – runs Control and Broadcast bots.
Celery Worker + Beat run as separate services in Docker Compose.
"""

import asyncio
import logging
import signal
import sys

from telegram.ext import ContextTypes

import logger
from src.broadcast import run_broadcast_bot
from src.control import run_control_bot
from src.db import close_db


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Update {update} caused error {context.error}")

async def run_bot(app, name: str):
    """Run a bot with proper shutdown handling."""
    if app.updater is None:
        logger.error(f"Error: {name} updater is not available.")
        return

    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def signal_handler():
        logger.info(f"Received termination signal, shutting down {name}...")
        shutdown_event.set()

    loop.add_signal_handler(signal.SIGINT, signal_handler)
    loop.add_signal_handler(signal.SIGTERM, signal_handler)

    logger.info(f"Starting {name}...")

    try:
        app.add_error_handler(error_handler)
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        logger.info(f"{name} is polling. Waiting for shutdown signal...")

        # ─── Block until a signal is received ──────────────────
        await shutdown_event.wait()

        logger.info(f"{name} shutting down...")
        await app.updater.stop()
        await app.stop()
    except Exception as e:
        logger.error(f"❌ {name} crashed: {e}")
    finally:
        await close_db()
        await app.shutdown()
        logger.shutdown_logging()
        logger.info(f"{name} stopped.")


async def main():
    """Start Control and Broadcast bots."""
    logger.info("Initializing bots...")
    control_app = await run_control_bot()
    broadcast_app = await run_broadcast_bot()

    logger.info("Running bots...")
    await asyncio.gather(
        run_bot(control_app, "Control bot"),
        run_bot(broadcast_app, "Broadcast bot"),
        return_exceptions=True,
    )


if __name__ == "__main__":
    logger.setup_logging(level=logging.INFO, log_file="coin_market_bot.log")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        sys.exit(0)
