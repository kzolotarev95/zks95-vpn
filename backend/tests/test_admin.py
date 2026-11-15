import time

import pyotp
import pytest
from app.core.encryption import encrypt
from app.core.security import hash_password, verify_password
from app.models.entities import AdminUser, AuditLog, Role, TelegramSettings, User
from sqlalchemy import select


@pytest.fixture
def admin_factory(client, db):
    def create(role_name="SuperAdmin", login=True):
        role = Role(name=role_name)
        db.add(role)
        db.flush()
        user = User(
            email=f"{role_name.lower()}@example.com",
            password_hash=hash_password("admin-password-for-test"),
        )
        db.add(user)
        db.flush()
        secret = pyotp.random_base32()
        db.add(
            AdminUser(
                user_id=user.id,
                role_id=role.id,
                mfa_enabled=True,
                totp_secret_encrypted=encrypt(secret),
            )
        )
        db.commit()
        body = {
            "email": user.email,
            "password": "admin-password-for-test",
            "otp": pyotp.TOTP(secret).now(),
        }
        if login:
            assert client.post("/api/v1/admin/login", json=body).status_code == 200
        return user, body, secret

    return create


def test_user_session_cannot_access_admin(client, account):
    assert client.get("/api/v1/admin/users").status_code == 401
    assert client.put("/api/v1/admin/telegram", json={"enabled": False}).status_code == 401


def test_admin_mfa_replay_and_session_isolation(client, db, admin_factory):
    user, body, secret = admin_factory(login=False)
    bad = {**body, "otp": "000000" if body["otp"] != "000000" else "111111"}
    assert client.post("/api/v1/admin/login", json=bad).status_code == 401
    assert client.post("/api/v1/admin/login", json=body).status_code == 200
    assert client.post("/api/v1/admin/login", json=body).status_code == 401
    assert client.get("/api/v1/admin/me").json()["role"] == "SuperAdmin"
    token = client.cookies.get("zks95_admin")
    client.cookies.set("zks95_session", token)
    assert client.get("/api/v1/me").status_code == 401
    assert db.get(AdminUser, user.id).last_totp_step >= int(time.time()) // 30 - 1
    assert client.post("/api/v1/admin/logout").status_code == 204
    assert client.get("/api/v1/admin/me").status_code == 401


def test_support_cannot_change_users_plans_or_bot(client, account, plan, admin_factory):
    admin_factory("Support")
    user_id = client.get("/api/v1/me").json()["id"]
    assert client.get("/api/v1/admin/users").status_code == 200
    assert (
        client.patch(f"/api/v1/admin/users/{user_id}", json={"is_active": False}).status_code == 403
    )
    assert client.get("/api/v1/admin/telegram").status_code == 403
    assert client.post("/api/v1/admin/plans", json={}).status_code == 403


def test_block_user_revokes_existing_sessions_and_is_audited(client, db, account, admin_factory):
    user_id = client.get("/api/v1/me").json()["id"]
    admin_factory()
    assert (
        client.patch(f"/api/v1/admin/users/{user_id}", json={"is_active": False}).status_code == 200
    )
    assert client.get("/api/v1/me").status_code == 401
    assert db.scalar(select(AuditLog).where(AuditLog.action == "user.block"))
    assert "password_hash" not in client.get("/api/v1/admin/users").text


def test_plan_change_does_not_reprice_existing_order(client, plan, account, admin_factory):
    order = client.post(
        "/api/v1/orders",
        json={"plan_id": str(plan.id)},
        headers={"Idempotency-Key": "snapshot-before-admin-edit"},
    ).json()
    admin_factory()
    response = client.put(
        f"/api/v1/admin/plans/{plan.id}",
        json={
            "code": plan.code,
            "name": "Новая цена",
            "description": plan.description,
            "price_minor": 49900,
            "duration_days": 60,
            "device_limit": 5,
            "is_active": False,
        },
    )
    assert response.status_code == 200
    assert client.get("/api/v1/plans").json() == []
    stored = client.get(f"/api/v1/orders/{order['id']}").json()
    assert stored["amount_minor"] == 19900
    assert stored["duration_days"] == 30
    assert stored["status"] == "pending"


def test_admin_cannot_block_self(client, admin_factory):
    user, _, _ = admin_factory()
    assert (
        client.patch(f"/api/v1/admin/users/{user.id}", json={"is_active": False}).status_code == 409
    )


def test_bot_token_encrypted_and_never_returned_to_admin(client, db, admin_factory, monkeypatch):
    admin_factory()
    token = "123456789:" + "x" * 35
    monkeypatch.setattr(
        "app.api.admin.validate_bot_token",
        lambda value: {
            "id": 123456789,
            "username": "zks95_test_bot",
            "is_bot": True,
        },
    )
    response = client.put("/api/v1/admin/telegram", json={"token": token, "enabled": True})
    assert response.status_code == 200
    assert token not in response.text
    row = db.get(TelegramSettings, 1)
    assert token not in row.token_encrypted
    assert token not in client.get("/api/v1/admin/telegram").text
    internal = client.get(
        "/api/v1/internal/bot/config",
        headers={"X-Bot-Service-Token": "test-service-token-used-only-in-isolated-tests"},
    )
    assert internal.json()["token"] == token
    assert client.get("/api/v1/internal/bot/config").status_code == 401


def test_admin_session_expiry(client, db, admin_factory):
    from datetime import timedelta

    from app.core.security import utcnow
    from app.models.entities import UserSession

    admin_factory()
    session = db.scalar(select(UserSession).where(UserSession.purpose == "admin"))
    session.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert client.get("/api/v1/admin/overview").status_code == 401


def test_default_admin_can_login_without_otp_and_change_password(client, db):
    role = Role(name="SuperAdmin")
    db.add(role)
    db.flush()
    user = User(email="admin", password_hash=hash_password("admin"))
    db.add(user)
    db.flush()
    db.add(AdminUser(user_id=user.id, role_id=role.id, mfa_enabled=False))
    db.commit()
    response = client.post("/api/v1/admin/login", json={"login": "admin", "password": "admin"})
    assert response.status_code == 200
    assert (
        client.post(
            "/api/v1/admin/password",
            json={"current_password": "admin", "new_password": "admin2"},
        ).status_code
        == 204
    )
    db.refresh(user)
    assert verify_password("admin2", user.password_hash)
