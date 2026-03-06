import redis
from rq import Queue

from app.core.config import settings

# Shared Redis connection and RQ task queue
redis_conn = redis.from_url(settings.REDIS_URL)
task_queue = Queue(connection=redis_conn)
