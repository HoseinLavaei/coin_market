"""
Manages Telegram job scheduling for active subscriptions.
Stores job references, handles removal, and supports immediate reloads
with instant updates using the broadcast bot instance.
"""

import asyncio
from decimal import Decimal
from typing import cast

from telegram.ext import Job, JobQueue, ContextTypes

from .data_provider import get_cached_data
from ..domain import ProviderName
from ..domain.value_objects import build_subscription_description
from ..infrastructure.models import Subscription
from ..infrastructure.repositories import get_active_subscriptions
from ..presentation.message_builder import build_prices_output

_subscription_jobs: dict[int, Job] = {}
_global_job_queue: JobQueue | None = None
_global_broadcast_bot = None  # used to send immediate updates from control bot


def set_job_queue(job_queue: JobQueue) -> None:
    """Store the job queue globally for reloads from the control bot."""
    global _global_job_queue
    _global_job_queue = job_queue


def set_broadcast_bot(bot) -> None:
    """Store the broadcast bot instance so other modules can send messages."""
    global _global_broadcast_bot
    _global_broadcast_bot = bot


def remove_subscription_job(sub_id: int) -> bool:
    """Remove and stop the job for a subscription ID. Returns True if removed."""
    global _subscription_jobs
    job = _subscription_jobs.get(sub_id)
    if job:
        job.schedule_removal()
        del _subscription_jobs[sub_id]
        print(f"Removed subscription job #{sub_id}")
        return True
    return False


async def send_market_data(
        chat_id: int,
        context: ContextTypes.DEFAULT_TYPE,
        provider: ProviderName | None = None,
        type_filter: str | None = None,
        volume: Decimal | None = None,
        is_auto: bool = False,
) -> None:
    """
    Build and send a market data message to the given chat.
    Retries up to 3 times on failure with 2‑second delays between attempts.
    """
    coins, orderbooks, updated_at = get_cached_data()
    filter_desc = build_subscription_description(
        provider.value if provider else None,
        type_filter,
        volume,
        None,
    )
    timestamp = updated_at.strftime('%H:%M:%S')
    content = build_prices_output(coins, orderbooks, provider, type_filter, volume)
    prefix = "🔄 Auto-update" if is_auto else "📊 Market data"
    msg = f"{prefix} ({filter_desc}, 🕒 updated at {timestamp})\n\n{content}"

    for attempt in range(3):
        try:
            if len(msg) > 4096:
                for i in range(0, len(msg), 4096):
                    await context.bot.send_message(chat_id=chat_id, text=msg[i:i + 4096])
            else:
                await context.bot.send_message(chat_id=chat_id, text=msg)
            return
        except Exception as e:
            print(f"⚠️ Send attempt {attempt + 1} failed for chat {chat_id}: {e}")
            if attempt < 2:
                await asyncio.sleep(2)
    print(f"❌ Failed to send message to chat {chat_id} after 3 attempts.")


async def send_subscription_update(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Job callback for a scheduled subscription update.
    Fires and forgets to avoid overlapping job runs.
    """
    job = context.job
    if job is None:
        return
    data = job.data
    if not isinstance(data, dict):
        return
    chat_id = data.get("chat_id")
    if chat_id is None:
        return
    chat_id = cast(int, chat_id)
    provider_name = data.get("provider")
    if isinstance(provider_name, str):
        provider = ProviderName[provider_name.upper()]
    else:
        provider = None
    type_filter = data.get("type_filter")
    volume = data.get("volume")

    asyncio.create_task(
        send_market_data(
            chat_id=chat_id,
            context=context,
            provider=provider,
            type_filter=type_filter,
            volume=volume,
            is_auto=True,
        )
    )


def schedule_subscription_job(job_queue: JobQueue, sub: Subscription) -> Job:
    """
    Schedule a repeating job for a subscription.
    The job sends updates at sub.repeat_interval seconds.
    """
    if sub.repeat_interval is None:
        raise ValueError("Cannot schedule a subscription without a repeat_interval")
    data = {
        "chat_id": sub.chat_id,
        "provider": sub.provider,
        "type_filter": sub.type_filter,
        "volume": sub.volume,
    }
    job = job_queue.run_repeating(
        send_subscription_update,
        interval=sub.repeat_interval,
        first=sub.repeat_interval,
        data=data,
    )
    return job


async def load_and_schedule_all_subscriptions(job_queue: JobQueue, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Load all active subscriptions from the database and schedule them.
    Also sends an immediate update for each subscription.
    Used during broadcast bot startup and cache refresh.
    """
    global _subscription_jobs
    subs = await get_active_subscriptions()
    for sub in subs:
        if sub.repeat_interval is None:
            continue
        job = schedule_subscription_job(job_queue, sub)
        _subscription_jobs[sub.id] = job
        print(f"Scheduled subscription #{sub.id} every {sub.repeat_interval}s")
        provider = ProviderName[sub.provider.upper()] if sub.provider else None
        await send_market_data(
            chat_id=sub.chat_id,
            context=context,
            provider=provider,
            type_filter=sub.type_filter,
            volume=sub.volume,
            is_auto=True,
        )


async def reload_subscriptions(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Reload all subscriptions – called during cache refresh from the broadcast bot.
    Stops and re‑schedules all jobs.
    """
    global _subscription_jobs
    for job in list(_subscription_jobs.values()):
        job.schedule_removal()
    _subscription_jobs.clear()
    await load_and_schedule_all_subscriptions(cast(JobQueue, context.job_queue), context)


async def reload_subscriptions_immediate() -> None:
    """
    Immediately reload all active subscriptions and send an immediate update.
    Called from the control bot after pause/resume/direct activation.
    Uses the stored broadcast bot to send messages.
    """
    global _subscription_jobs, _global_job_queue, _global_broadcast_bot
    if _global_job_queue is None or _global_broadcast_bot is None:
        print("❌ Cannot reload subscriptions: job queue or broadcast bot not set.")
        return

    # Remove all currently scheduled jobs
    for job in list(_subscription_jobs.values()):
        job.schedule_removal()
    _subscription_jobs.clear()

    # Reload active subscriptions and schedule them
    subs = await get_active_subscriptions()
    for sub in subs:
        if sub.repeat_interval is None:
            continue
        job = schedule_subscription_job(_global_job_queue, sub)
        _subscription_jobs[sub.id] = job
        print(f"🔄 Reloaded subscription #{sub.id} every {sub.repeat_interval}s")

        # Send immediate update using the broadcast bot
        provider = ProviderName[sub.provider.upper()] if sub.provider else None
        dummy_context = type('DummyContext', (), {'bot': _global_broadcast_bot})()
        await send_market_data(
            chat_id=sub.chat_id,
            context=dummy_context,
            provider=provider,
            type_filter=sub.type_filter,
            volume=sub.volume,
            is_auto=True,
        )

    print("✅ Subscriptions reloaded and immediate updates sent.")
