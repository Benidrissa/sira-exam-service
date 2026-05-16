from celery import Celery
from kombu import Queue

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
    # Dedicated queue so sira tasks don't mix with etutor's default "celery" queue
    task_default_queue="sira_exam",
    task_queues=(
        Queue("sira_exam"),
        Queue("sira_exam_high"),
        Queue("sira_exam_low"),
    ),
    task_routes={
        "tasks.analyze_snapshot": {"queue": "sira_exam"},
        "tasks.check_heartbeat": {"queue": "sira_exam"},
        "tasks.finalize_session": {"queue": "sira_exam"},
        "tasks.check_edge_anomalies": {"queue": "sira_exam"},
    },
    beat_schedule={
        "check-heartbeat-every-30s": {
            "task": "tasks.check_heartbeat",
            "schedule": 30.0,  # every 30 seconds
        },
        "check-edge-anomalies-every-5min": {
            "task": "tasks.check_edge_anomalies",
            "schedule": 300.0,  # every 5 minutes — E3-14
        },
    },
)
