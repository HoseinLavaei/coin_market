"""
Control bot – menu‑only.
All interactions go through the inline keyboard menu.
Only /start and /menu are supported.
"""

import asyncio
import signal
import sys

from telegram.ext import ApplicationBuilder

from .inline_keyboard import control_conversation
from ..environment import CONTROL_BOT_TOKEN
from ..infrastructure import close_db


async def run_control_bot():
    """
    Main entry point for the control bot.
    Only the menu system is used – no direct command handlers.
    """
    while True:
        try:
            if not CONTROL_BOT_TOKEN:
                print("Error: CONTROL_BOT_TOKEN environment variable not set.")
                sys.exit(1)

            app = ApplicationBuilder().token(CONTROL_BOT_TOKEN).build()

            # ─── Only the conversation handler ────────────────
            # Handles /start, /menu, and all inline interactions.
            # All other commands are ignored.
            app.add_handler(control_conversation)

            print("Control bot started.")
            print("Use /start or /menu to open the menu. All other commands are ignored.")

            await app.initialize()
            await app.start()

            if app.updater is None:
                print("Error: Updater is not available.")
                sys.exit(1)

            await app.updater.start_polling()

            shutdown_event = asyncio.Event()
            loop = asyncio.get_running_loop()

            def signal_handler():
                print("Received termination signal, shutting down control bot...")
                shutdown_event.set()

            loop.add_signal_handler(signal.SIGINT, signal_handler)
            loop.add_signal_handler(signal.SIGTERM, signal_handler)

            await shutdown_event.wait()

            print("EXITING control bot...")
            if app.updater:
                await app.updater.stop()
            await app.stop()
            await close_db()
            await app.shutdown()
            break

        except Exception as e:
            print(f"❌ Control bot crashed: {e}")
            import traceback
            traceback.print_exc()
            print("🔄 Restarting control bot in 5 seconds...")
            await asyncio.sleep(5)