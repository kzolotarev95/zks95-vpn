import uuid
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

from app.core.security import utcnow
from app.models.entities import TelegramAccount, TelegramLink, TelegramSettings
from sqlalchemy import select

SERVICE = {"X-Bot-Service-Token": "test-service-token-used-only-in-isolated-tests"}


def test_bot_service_requires_secret_even_without_origin(client):
    client.headers.pop("origin")
    assert (
        client.post(
            "/api/v1/internal/bot/account", json={"telegram_id": 10001, "display_name": "Tester"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/internal/bot/account",
            json={"telegram_id": 10001, "display_name": "Tester"},
            headers=SERVICE,
        ).status_code
        == 200
    )
    assert client.post("/api/v1/auth/register", json={}).status_code == 403


def test_telegram_user_order_is_idempotent_and_unpaid(client, db, plan):
    body = {"telegram_id": 10002, "display_name": "Tester", "username": "tester"}
    first = client.post("/api/v1/internal/bot/account", json=body, headers=SERVICE)
    second = client.post("/api/v1/internal/bot/account", json=body, headers=SERVICE)
    assert first.json() == second.json()
    assert len(list(db.scalars(select(TelegramAccount)))) == 1
    order = {"telegram_id": 10002, "plan_id": str(plan.id), "idempotency_key": str(uuid.uuid4())}
    created = client.post("/api/v1/internal/bot/orders", json=order, headers=SERVICE)
    assert created.status_code == 201
    assert created.json()["status"] == "pending"
    assert (
        client.post("/api/v1/internal/bot/orders", json=order, headers=SERVICE).json()
        == created.json()
    )
    snapshot = client.get("/api/v1/internal/bot/users/10002/snapshot", headers=SERVICE).json()
    assert snapshot["subscriptions"] == []
    assert len(snapshot["orders"]) == 1


def test_one_time_link_connects_existing_website_user(client, db, account):
    user_id = client.get("/api/v1/me").json()["id"]
    db.add(TelegramSettings(id=1, username="zks95_test_bot", enabled=True, revision=1))
    db.commit()
    link = client.post("/api/v1/me/telegram-link").json()
    token = parse_qs(urlsplit(link["url"]).query)["start"][0][5:]
    body = {"telegram_id": 10003, "display_name": "Website user", "link_token": token}
    response = client.post("/api/v1/internal/bot/account", json=body, headers=SERVICE)
    assert response.status_code == 200
    assert response.json()["user_id"] == user_id
    assert (
        client.post("/api/v1/internal/bot/account", json=body, headers=SERVICE).status_code == 422
    )
    assert client.get("/api/v1/me/telegram").json()["linked"] is True


def test_expired_link_cannot_be_used(client, db, account):
    db.add(TelegramSettings(id=1, username="zks95_test_bot", enabled=True, revision=1))
    db.commit()
    link = client.post("/api/v1/me/telegram-link").json()
    stored = db.scalar(select(TelegramLink))
    stored.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    token = parse_qs(urlsplit(link["url"]).query)["start"][0][5:]
    assert (
        client.post(
            "/api/v1/internal/bot/account",
            json={
                "telegram_id": 10004,
                "display_name": "Tester",
                "link_token": token,
            },
            headers=SERVICE,
        ).status_code
        == 422
    )


def test_bot_cannot_take_over_existing_identity(client, db, account):
    client.post(
        "/api/v1/internal/bot/account",
        json={"telegram_id": 10005, "display_name": "Original account"},
        headers=SERVICE,
    )
    db.add(TelegramSettings(id=1, username="zks95_test_bot", enabled=True, revision=1))
    db.commit()
    link = client.post("/api/v1/me/telegram-link").json()
    token = parse_qs(urlsplit(link["url"]).query)["start"][0][5:]
    assert (
        client.post(
            "/api/v1/internal/bot/account",
            json={"telegram_id": 10005, "display_name": "Attempt", "link_token": token},
            headers=SERVICE,
        ).status_code
        == 409
    )
