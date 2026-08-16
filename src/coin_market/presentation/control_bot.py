"""
Control bot – handles subscription creation (key‑based or direct via --chat_id),
listing, pausing, resuming, and deletion of subscriptions.
"""

import asyncio
import secrets
import signal
import sys
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from .constants import USAGE_MESSAGE
from .parsers import parse_prices_args
from ..domain import build_subscription_description
from ..environment import CONTROL_BOT_TOKEN, KEY_EXPIRY_SECONDS, TIMEZONE
from ..infrastructure.repositories import (
    create_pending_subscription,
    get_subscriptions_for_user,
    pause_subscription_by_id,
    resume_subscription_by_id,
    delete_subscription_by_id,
    add_subscription,
)
from ..services.subscription_scheduler import (
    remove_subscription_job,
    reload_subscriptions_immediate,
)


# ─── Helper Functions for prices_command ────────────────────

async def _activate_subscription_directly(
        user_id: int,
        provider,
        type_filter: str | None,
        volume,
        repeat_interval: int,
        chat_id: int,
) -> str:
    """
    Create an active subscription immediately for the given chat_id.
    No key is required; the broadcast bot sends the first update.
    """
    try:
        await add_subscription(
            chat_id=chat_id,
            user_id=user_id,
            provider=provider.value if provider else None,
            type_filter=type_filter,
            volume=volume,
            repeat_interval=repeat_interval,
        )
        await reload_subscriptions_immediate()

        filter_desc = build_subscription_description(
            provider.value if provider else None,
            type_filter,
            volume,
            None,
        )
        return (
            f"✅ Subscription activated!\n"
            f"Filters: {filter_desc}\n"
            f"Repeat every: {repeat_interval}s\n"
            f"Chat ID: {chat_id}\n"
            f"First update sent immediately."
        )
    except Exception as e:
        return f"❌ Failed to create subscription: {e}"


async def _create_pending_subscription_flow(
        user_id: int,
        provider,
        type_filter: str | None,
        volume,
        repeat_interval: int,
) -> str:
    """
    Create a pending subscription with a one‑time key.
    The user must send the key to the broadcast bot from the target chat.
    """
    key = secrets.token_hex(4).upper()
    expires_at = datetime.now(TIMEZONE) + timedelta(seconds=KEY_EXPIRY_SECONDS)
    try:
        await create_pending_subscription(
            key=key,
            user_id=user_id,
            provider=provider.value if provider else None,
            type_filter=type_filter,
            volume=volume,
            repeat_interval=repeat_interval,
            expires_at=expires_at,
        )
        filter_desc = build_subscription_description(
            provider.value if provider else None,
            type_filter,
            volume,
            None,
        )
        return (
            f"✅ Subscription request created!\n\n"
            f"Filters: {filter_desc}\n"
            f"Repeat every: {repeat_interval}s\n\n"
            f"To activate, send this key in the chat where you want updates:\n"
            f"🔑 `{key}`\n\n"
            f"Use `/conf {key}` in that chat (valid for {KEY_EXPIRY_SECONDS} seconds)."
        )
    except Exception as e:
        return f"❌ Failed to create subscription request: {e}"


# ─── Command Handlers ──────────────────────────────────────

async def prices_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Create a subscription (either direct or key‑based).
    If --chat_id is provided, activate immediately; otherwise create a pending key.
    """
    message = update.effective_message
    if message is None:
        return
    user = update.effective_user
    if user is None:
        await message.reply_text("❌ Could not determine user. Please try again.")
        return

    args = context.args or []
    try:
        provider, type_filter, volume, repeat_interval, _, chat_id = parse_prices_args(args)
    except ValueError as e:
        await message.reply_text(f"❌ Error parsing filters: {e}\n\n{USAGE_MESSAGE}")
        return

    if repeat_interval is None:
        await message.reply_text(
            "ℹ️ One-time /prices requests are not supported. Use --repeat to create a subscription."
        )
        return

    if chat_id is not None:
        response = await _activate_subscription_directly(
            user.id, provider, type_filter, volume, repeat_interval, chat_id
        )
    else:
        response = await _create_pending_subscription_flow(
            user.id, provider, type_filter, volume, repeat_interval
        )

    await message.reply_text(response)


async def list_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all subscriptions belonging to the user."""
    message = update.effective_message
    if message is None:
        return
    user = update.effective_user
    if user is None:
        await message.reply_text("❌ Could not determine user. Please try again.")
        return
    user_id = user.id
    subs = await get_subscriptions_for_user(user_id)
    if not subs:
        await message.reply_text("📭 You have no subscriptions.")
        return
    lines = ["📋 Your subscriptions:"]
    for sub in subs:
        status_emoji = "✅" if sub.status == "active" else "⏸️"
        desc = build_subscription_description(
            sub.provider,
            sub.type_filter,
            sub.volume,
            sub.repeat_interval,
        )
        lines.append(f"  {status_emoji} #{sub.id}: {desc} (chat: {sub.chat_id}, status: {sub.status})")
    msg = "\n".join(lines)
    if len(msg) > 4096:
        for i in range(0, len(msg), 4096):
            await message.reply_text(msg[i:i + 4096])
    else:
        await message.reply_text(msg)


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pause a subscription by its ID."""
    message = update.effective_message
    if message is None:
        return
    user = update.effective_user
    if user is None:
        await message.reply_text("❌ Could not determine user. Please try again.")
        return
    user_id = user.id
    args = context.args or []
    if not args:
        await message.reply_text("❌ Please provide subscription ID: /stop <id>")
        return
    try:
        sub_id = int(args[0])
    except ValueError:
        await message.reply_text("❌ Invalid ID. Please provide a number.")
        return
    count = await pause_subscription_by_id(sub_id, user_id)
    if count:
        remove_subscription_job(sub_id)
        await reload_subscriptions_immediate()
        await message.reply_text(f"⏸️ Paused subscription #{sub_id}.")
    else:
        await message.reply_text(f"❌ Subscription #{sub_id} not found or not yours.")


async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Resume a paused subscription by its ID."""
    message = update.effective_message
    if message is None:
        return
    user = update.effective_user
    if user is None:
        await message.reply_text("❌ Could not determine user. Please try again.")
        return
    user_id = user.id
    args = context.args or []
    if not args:
        await message.reply_text("❌ Please provide subscription ID: /resume <id>")
        return
    try:
        sub_id = int(args[0])
    except ValueError:
        await message.reply_text("❌ Invalid ID. Please provide a number.")
        return
    count = await resume_subscription_by_id(sub_id, user_id)
    if count:
        await reload_subscriptions_immediate()
        await message.reply_text(f"▶️ Resumed subscription #{sub_id}.")
    else:
        await message.reply_text(f"❌ Subscription #{sub_id} not found, not paused, or not yours.")


async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Permanently delete a subscription by its ID."""
    message = update.effective_message
    if message is None:
        return
    user = update.effective_user
    if user is None:
        await message.reply_text("❌ Could not determine user. Please try again.")
        return
    user_id = user.id
    args = context.args or []
    if not args:
        await message.reply_text("❌ Please provide subscription ID: /delete <id>")
        return
    try:
        sub_id = int(args[0])
    except ValueError:
        await message.reply_text("❌ Invalid ID. Please provide a number.")
        return
    count = await delete_subscription_by_id(sub_id, user_id)
    if count:
        remove_subscription_job(sub_id)
        await message.reply_text(f"🗑️ Deleted subscription #{sub_id}.")
    else:
        await message.reply_text(f"❌ Subscription #{sub_id} not found or not yours.")


async def help_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the help message for the control bot."""
    message = update.effective_message
    if message is None:
        return
    await message.reply_text(
        "🤖 Control Bot\n\n"
        "This bot creates and manages market data subscriptions.\n\n"
        f"Commands:\n{USAGE_MESSAGE}\n\n"
        "Without --chat_id, you will receive a one‑time key.\n"
        "Send that key (/conf KEY) to the broadcast bot in the chat where you want updates.\n\n"
        "With --chat_id, the subscription is activated immediately and the first update is sent."
    )


# ─── Bot Lifecycle ──────────────────────────────────────────

async def run_control_bot():
    """
    Main entry point for the control bot. Sets up handlers and starts polling.
    Restarts automatically on crash.
    """
    while True:
        try:
            if not CONTROL_BOT_TOKEN:
                print("Error: CONTROL_BOT_TOKEN environment variable not set.")
                sys.exit(1)

            app = ApplicationBuilder().token(CONTROL_BOT_TOKEN).build()
            app.add_handler(CommandHandler("prices", prices_command))
            app.add_handler(CommandHandler("list", list_command))
            app.add_handler(CommandHandler("stop", stop_command))
            app.add_handler(CommandHandler("resume", resume_command))
            app.add_handler(CommandHandler("delete", delete_command))
            app.add_handler(CommandHandler("help", help_command))
            print("Control bot started.")
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
            await app.shutdown()
            break

        except Exception as e:
            print(f"❌ Control bot crashed: {e}")
            import traceback
            traceback.print_exc()
            print("🔄 Restarting control bot in 5 seconds...")
            await asyncio.sleep(5)
