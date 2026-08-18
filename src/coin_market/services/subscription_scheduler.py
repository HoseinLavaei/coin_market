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
_global_broadcast_bot = None


def set_job_queue(job_queue: JobQueue) -> None:
    global _global_job_queue
    _global_job_queue = job_queue


def set_broadcast_bot(bot) -> None:
    global _global_broadcast_bot
    _global_broadcast_bot = bot


def remove_subscription_job(sub_id: int) -> bool:
    global _subscription_jobs
    job = _subscription_jobs.get(sub_id)
    if job:
        job.schedule_removal()
        del _subscription_jobs[sub_id]
        print(f"Removed subscription job #{sub_id}")
        return True
    return False


# ─── Helper: Build market data message ──────────────────────

def _build_market_data_message(
        provider: ProviderName | str | None,
        type_filter: str | None,
        volume: Decimal | None,
        is_auto: bool,
) -> str:
    """Build the market data message text."""
    coins, orderbooks, updated_at = get_cached_data()

    # Convert provider to string for description
    provider_str_for_desc: str | None
    if isinstance(provider, ProviderName):
        provider_str_for_desc = provider.value
    else:
        provider_str_for_desc = provider

    filter_desc = build_subscription_description(
        provider_str_for_desc,
        type_filter,
        volume,
        None,
    )
    timestamp = updated_at.strftime('%H:%M:%S')
    content = build_prices_output(coins, orderbooks, provider, type_filter, volume)
    prefix = "🔄 Auto-update" if is_auto else "📊 Market data"
    return f"{prefix} ({filter_desc}, 🕒 updated at {timestamp})\n\n{content}"


# ─── Helper: Send with retry ────────────────────────────────

async def _send_with_retry(
        chat_id: int,
        text: str,
        context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Send a message with up to 3 retries."""
    for attempt in range(3):
        try:
            if len(text) > 4096:
                for i in range(0, len(text), 4096):
                    await context.bot.send_message(chat_id=chat_id, text=text[i:i + 4096])
            else:
                await context.bot.send_message(chat_id=chat_id, text=text)
            return
        except Exception as e:
            print(f"⚠️ Send attempt {attempt + 1} failed for chat {chat_id}: {e}")
            if attempt < 2:
                await asyncio.sleep(2)
    print(f"❌ Failed to send message to chat {chat_id} after 3 attempts.")


# ─── Main send function ──────────────────────────────────────

async def send_market_data(
        chat_id: int,
        context: ContextTypes.DEFAULT_TYPE,
        provider: ProviderName | str | None = None,
        type_filter: str | None = None,
        volume: Decimal | None = None,
        is_auto: bool = False,
) -> None:
    """
    Build and send a market data message to the given chat.
    Retries up to 3 times on failure.
    """
    text = _build_market_data_message(provider, type_filter, volume, is_auto)
    await _send_with_retry(chat_id, text, context)


async def send_subscription_update(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job callback for a scheduled subscription update."""
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

    provider = data.get("provider")
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
    global _subscription_jobs
    subs = await get_active_subscriptions()
    for sub in subs:
        if sub.repeat_interval is None:
            continue
        job = schedule_subscription_job(job_queue, sub)
        _subscription_jobs[sub.id] = job
        print(f"Scheduled subscription #{sub.id} every {sub.repeat_interval}s")
        await send_market_data(
            chat_id=sub.chat_id,
            context=context,
            provider=sub.provider,
            type_filter=sub.type_filter,
            volume=sub.volume,
            is_auto=True,
        )


async def reload_subscriptions(context: ContextTypes.DEFAULT_TYPE) -> None:
    global _subscription_jobs
    for job in list(_subscription_jobs.values()):
        job.schedule_removal()
    _subscription_jobs.clear()
    await load_and_schedule_all_subscriptions(cast(JobQueue, context.job_queue), context)


async def reload_subscriptions_immediate() -> None:
    global _subscription_jobs, _global_job_queue, _global_broadcast_bot
    if _global_job_queue is None or _global_broadcast_bot is None:
        print("❌ Cannot reload subscriptions: job queue or broadcast bot not set.")
        return

    for job in list(_subscription_jobs.values()):
        job.schedule_removal()
    _subscription_jobs.clear()

    subs = await get_active_subscriptions()
    for sub in subs:
        if sub.repeat_interval is None:
            continue
        job = schedule_subscription_job(_global_job_queue, sub)
        _subscription_jobs[sub.id] = job
        print(f"🔄 Reloaded subscription #{sub.id} every {sub.repeat_interval}s")
        dummy_context = type('DummyContext', (), {'bot': _global_broadcast_bot})()
        await send_market_data(
            chat_id=sub.chat_id,
            context=dummy_context,
            provider=sub.provider,
            type_filter=sub.type_filter,
            volume=sub.volume,
            is_auto=True,
        )

    print("✅ Subscriptions reloaded and immediate updates sent.")
