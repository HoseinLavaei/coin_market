"""
Celery tasks package.
Exports the task so it can be imported.
"""

from .send_updates import send_due_updates
