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
_global_job_queue: JobQueue | None = None  # set by broadcast_bot


def set_job_queue(job_queue: JobQueue) -> None:
    """Set the global job queue (called once at broadcast bot startup)."""
    global _global_job_queue
    _global_job_queue = job_queue


async def reload_subscriptions_immediate() -> None:
    """
    Immediately reload all active subscriptions from the database.
    Can be called from any module (e.g., control_bot) to apply pause/resume instantly.
    """
    global _subscription_jobs, _global_job_queue
    if _global_job_queue is None:
        print("❌ Cannot reload subscriptions: job queue not set.")
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

    print("✅ Subscriptions reloaded.")


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
    if len(msg) > 4096:
        for i in range(0, len(msg), 4096):
            await context.bot.send_message(chat_id=chat_id, text=msg[i:i + 4096])
    else:
        await context.bot.send_message(chat_id=chat_id, text=msg)


async def send_subscription_update(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    if job is None:
        return
    data = job.data
    if not isinstance(data, dict):
        return
    chat_id = data.get("chat_id")
    if chat_id is None:
        return
    else:
        chat_id = cast(int, chat_id)
    provider_name = data.get("provider")
    if isinstance(provider_name, str):
        provider = ProviderName[provider_name.upper()]
    else:
        provider = None
    type_filter = data.get("type_filter")
    volume = data.get("volume")
    await send_market_data(
        chat_id=chat_id,
        context=context,
        provider=provider,
        type_filter=type_filter,
        volume=volume,
        is_auto=True,
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
        provider = ProviderName[sub.provider.upper()] if sub.provider else None
        if context.bot:
            await send_market_data(
                chat_id=sub.chat_id,
                context=context,
                provider=provider,
                type_filter=sub.type_filter,
                volume=sub.volume,
                is_auto=True,
            )
        else:
            print(f"⚠️ Skipped initial message for subscription #{sub.id} (no bot in context)")


async def reload_subscriptions(context: ContextTypes.DEFAULT_TYPE) -> None:
    global _subscription_jobs
    for job in list(_subscription_jobs.values()):
        job.schedule_removal()
    _subscription_jobs.clear()
    await load_and_schedule_all_subscriptions(cast(JobQueue, context.job_queue), context)