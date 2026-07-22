import redis
from redis.lock import Lock

from app.core.config import settings

# seperate db for locks so they don't cause troubles with result and celery setup
redis_client = redis.Redis.from_url(f"{settings.redis_url}/2", decode_responses=True)

# Auto Expire locks after 10 minutes to avoid deadlocks in case of worker crashes
WORKSPACE_ALIGNMENT_LOCK_TIMEOUT = 600


def workspace_alignment_lock(workspace_id: str) -> Lock:
    """Redis-backed mutex ensuring at most one cross-document alignment runs per
    workspace at a time. Cross-document align relies on other runs having written their entities.
    If both would run concurrently this cannot be ensured.
    """
    return redis_client.lock(
        f"lock:cross-alignment:{workspace_id}",
        timeout=WORKSPACE_ALIGNMENT_LOCK_TIMEOUT,
    )
