import hashlib
from functools import lru_cache

from fastapi import HTTPException, Request
from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings

_INCREMENT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return count
"""


@lru_cache
def get_redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, socket_connect_timeout=2, socket_timeout=2)


def rate_limit(request: Request, bucket: str, limit: int, seconds: int) -> None:
    if not get_settings().rate_limit_enabled:
        return
    # Uvicorn trusts proxy headers only from the dedicated nginx network in production.
    address = request.client.host if request.client else "unknown"
    identity = hashlib.sha256(address.encode()).hexdigest()
    key = f"limit:{bucket}:{identity}"
    try:
        count = get_redis().eval(_INCREMENT, 1, key, seconds)
    except RedisError as exc:
        raise HTTPException(503, "Сервис временно недоступен") from exc
    if int(count) > limit:
        raise HTTPException(429, "Слишком много запросов", headers={"Retry-After": str(seconds)})
