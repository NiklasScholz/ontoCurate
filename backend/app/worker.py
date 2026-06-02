from celery import Celery

from app.core.config import settings

celery_app = Celery("ontocurate")

celery_app.conf.update(
    broker_url=f"{settings.redis_url}/0",
    result_backend=f"{settings.redis_url}/1",
    result_expires=3600,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
)

celery_app.autodiscover_tasks(["app"])
