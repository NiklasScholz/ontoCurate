from celery import Celery

from app.core.config import settings
from celery.signals import worker_process_init

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


@worker_process_init.connect
def apply_ontogpt_patches(**kwargs):
    """Apply ontoGPT patches before any worker processes are starting."""
    from ontogpt_patches.apply_patches import apply_patches
    apply_patches()
