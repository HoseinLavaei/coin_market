"""
Scheduler package – Celery app and tasks.
"""

from .celery_app import app as celery_app
from .tasks import send_due_updates
