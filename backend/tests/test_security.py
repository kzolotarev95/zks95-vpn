from unittest.mock import Mock

import pytest
from app.core.config import Settings
from app.core.limiter import rate_limit
from fastapi import HTTPException
from redis.exceptions import ConnectionError as RedisConnectionError


def test_production_configuration_rejects_insecure_defaults():
    with pytest.raises(ValueError, match="HTTPS"):
        Settings(environment="production")


def test_rate_limit_fails_closed(monkeypatch):
    import app.core.limiter as limiter

    monkeypatch.setattr(limiter, "get_settings", lambda: Mock(rate_limit_enabled=True))
    redis = Mock()
    monkeypatch.setattr(limiter, "get_redis", lambda: redis)
    request = Mock(client=Mock(host="192.0.2.1"))
    redis.eval.return_value = 11
    with pytest.raises(HTTPException) as error:
        rate_limit(request, "login", 10, 300)
    assert error.value.status_code == 429
    redis.eval.side_effect = RedisConnectionError("unavailable")
    with pytest.raises(HTTPException) as error:
        rate_limit(request, "login", 10, 300)
    assert error.value.status_code == 503


def test_security_headers_and_liveness(client):
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"] == "no-store"
