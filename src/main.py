"""
Main entry point for the application.
Runs the broadcast and control bots concurrently in the same event loop.
"""

import asyncio
import sys

from coin_market.presentation import run_broadcast_bot, run_control_bot


async def main():
    """
    Start both bots simultaneously. Exceptions are caught and logged
    by each bot's own restart loop, so we use return_exceptions=True
    to prevent one failing from terminating the other.
    """
    await asyncio.gather(
        run_broadcast_bot(),
        run_control_bot(),
        return_exceptions=True
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down...")
        sys.exit(0)
