"""
Celery app with beat schedule (every minute).
"""

from celery import Celery

from src.environment import REDIS_URL

# ─── Create Celery app ──────────────────────────────────────
app = Celery("coin_market")

app.config_from_object({
    "broker_url": REDIS_URL,
    "result_backend": REDIS_URL,
    "task_serializer": "json",
    "result_serializer": "json",
    "accept_content": ["json"],
    "timezone": "UTC",
    "enable_utc": True,
    "beat_schedule": {
        "send-updates-every-minute": {
            "task": "scheduler.tasks.send_updates.send_due_updates",
            "schedule": 60.0,
            "options": {"expires": 55.0},
        },
    },
})

# ─── Auto-discover tasks ────────────────────────────────────
app.autodiscover_tasks(["scheduler.tasks"])
