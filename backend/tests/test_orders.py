import uuid
from datetime import timedelta

from app.core.security import utcnow
from app.models.entities import Order, Subscription
from sqlalchemy import func, select


def order_request(client, plan, key=None):
    return client.post(
        "/api/v1/orders",
        json={"plan_id": str(plan.id)},
        headers={"Idempotency-Key": key or str(uuid.uuid4())},
    )


def test_orders_require_authentication(client, plan):
    assert order_request(client, plan).status_code == 401
    assert client.get("/api/v1/orders").status_code == 401


def test_order_does_not_activate_subscription(client, db, plan, account):
    response = order_request(client, plan)
    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert response.json()["amount_minor"] == 19900
    assert client.get("/api/v1/subscriptions").json() == []
    assert db.scalar(select(func.count()).select_from(Subscription)) == 0


def test_idempotency_and_price_snapshot(client, db, plan, account):
    key = str(uuid.uuid4())
    first = order_request(client, plan, key).json()
    plan.price_minor = 39900
    plan.is_active = False
    db.commit()
    second = order_request(client, plan, key)
    assert second.status_code == 201
    assert second.json() == first
    assert db.scalar(select(func.count()).select_from(Order)) == 1
    assert order_request(client, plan).status_code == 404


def test_client_cannot_override_price_or_payment_state(client, plan, account):
    response = client.post(
        "/api/v1/orders",
        json={"plan_id": str(plan.id), "amount_minor": 1, "status": "paid"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 422


def test_foreign_order_is_inaccessible(client, plan, account):
    order = order_request(client, plan).json()
    assert client.post("/api/v1/auth/logout").status_code == 204
    client.post(
        "/api/v1/auth/register",
        json={"email": "another@example.com", "password": "another-long-password"},
    )
    assert client.get(f"/api/v1/orders/{order['id']}").status_code == 404
    assert client.get("/api/v1/orders").json() == []
    assert client.get("/api/v1/subscriptions").json() == []


def test_catalog_filters_inactive_plans(client, db, plan):
    assert len(client.get("/api/v1/plans").json()) == 1
    plan.is_active = False
    db.commit()
    assert client.get("/api/v1/plans").json() == []


def test_expired_subscription_not_reported_as_active(client, db, plan, account):
    order = order_request(client, plan).json()
    stored = db.get(Order, uuid.UUID(order["id"]))
    stored.status = "paid"
    db.add(
        Subscription(
            user_id=stored.user_id,
            order_id=stored.id,
            plan_name="Месяц",
            device_limit=3,
            starts_at=utcnow() - timedelta(days=31),
            expires_at=utcnow() - timedelta(days=1),
            status="active",
        )
    )
    db.commit()
    assert client.get("/api/v1/subscriptions").json()[0]["status"] == "expired"
