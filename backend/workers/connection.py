"""Redis connection and RQ queue setup."""
import os
import redis
from rq import Queue

# Redis connection
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_conn = redis.from_url(redis_url, decode_responses=False)

# Queues with different priorities
# high: urgent tasks (e.g., small quick pipelines)
# default: normal pipeline runs
# low: batch processing, exports
high_queue = Queue('high', connection=redis_conn)
default_queue = Queue('default', connection=redis_conn)
low_queue = Queue('low', connection=redis_conn)
