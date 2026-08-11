import asyncio
import sys

from coin_market.presentation import run_broadcast_bot, run_control_bot


async def main():
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
