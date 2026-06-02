import logging
import time

from app.worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="debug.ping")
def ping_task(message: str = "pong") -> str:
    """Task to verify Celery Workers are receiving tasks sucessfully"""
    logger.info("[debug.ping] received: %s", message)
    return message


@celery_app.task(name="debug.slow")
def slow_task(seconds: int = 5) -> str:
    """Test to check for async behaviour of celery workers"""
    logger.info("[debug.slow] sleeping for %s seconds", seconds)
    time.sleep(seconds)
    logger.info("[debug.slow] done")
    return f"slept for {seconds}s"
