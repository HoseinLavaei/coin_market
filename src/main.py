"""
Main entry point – runs Control and Broadcast bots.
Celery Worker + Beat run as separate services in Docker Compose.
"""

import asyncio
import signal
import sys

from src.broadcast import run_broadcast_bot
from src.control import run_control_bot
from src.db import close_db


async def run_bot(app, name: str):
    """Run a bot with proper shutdown handling."""
    if app.updater is None:
        print(f"Error: {name} updater is not available.")
        return

    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def signal_handler():
        print(f"Received termination signal, shutting down {name}...")
        shutdown_event.set()

    loop.add_signal_handler(signal.SIGINT, signal_handler)
    loop.add_signal_handler(signal.SIGTERM, signal_handler)

    print(f"Starting {name}...")

    try:
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        print(f"{name} is polling. Waiting for shutdown signal...")

        # ─── Block until a signal is received ──────────────────
        await shutdown_event.wait()

        print(f"{name} shutting down...")
        await app.updater.stop()
        await app.stop()
    except Exception as e:
        print(f"❌ {name} crashed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await close_db()
        await app.shutdown()
        print(f"{name} stopped.")


async def main():
    """Start Control and Broadcast bots."""
    print("Initializing bots...")
    control_app = await run_control_bot()
    broadcast_app = await run_broadcast_bot()

    print("Running bots...")
    await asyncio.gather(
        run_bot(control_app, "Control bot"),
        run_bot(broadcast_app, "Broadcast bot"),
        return_exceptions=True,
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down...")
        sys.exit(0)
