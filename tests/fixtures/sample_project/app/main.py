import os

import redis

cache = redis.Redis.from_url(os.environ["REDIS_URL"])
DATABASE_URL = os.getenv("DATABASE_URL")


def handler(key):
    order = cache.get(key)
    return order
