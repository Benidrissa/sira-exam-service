from celery import Celery
from celery.schedules import crontab  # noqa: F401

from app.core.config import settings

celery_app = Celery(
    "sira_exam",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.extraction",
        "app.tasks.generation",
        "app.tasks.proctor_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "check-heartbeat-every-30s": {
            "task": "tasks.check_heartbeat",
            "schedule": 30.0,  # every 30 seconds
        },
    },
)
