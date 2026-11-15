from datetime import timedelta

from app.core.security import utcnow
from app.models.entities import AuditLog, User, UserSession
from sqlalchemy import select


def test_register_login_logout_revokes_token(client, db, account):
    user = client.get("/api/v1/me")
    assert user.status_code == 200
    assert "password" not in user.text
    stored = db.scalar(select(User))
    assert stored.password_hash.startswith("$argon2id$")
    token = client.cookies.get("zks95_session")
    assert db.scalar(select(UserSession)).token_hash != token
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/me").status_code == 401
    client.cookies.set("zks95_session", token)
    assert client.get("/api/v1/me").status_code == 401
    response = client.post("/api/v1/auth/login", json=account)
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    assert db.scalar(select(AuditLog).where(AuditLog.action == "auth.login"))


def test_invalid_login_and_duplicate_registration(client, account):
    assert client.post("/api/v1/auth/register", json=account).status_code == 409
    bad = {**account, "password": "wrong-password-at-least-twelve"}
    assert client.post("/api/v1/auth/login", json=bad).status_code == 401
    assert (
        client.post("/api/v1/auth/login", json={**bad, "email": "missing@example.com"}).status_code
        == 401
    )


def test_reject_csrf_on_login_and_missing_origin(client, account):
    assert (
        client.post(
            "/api/v1/auth/login", json=account, headers={"Origin": "https://attacker.invalid"}
        ).status_code
        == 403
    )
    client.headers.pop("origin")
    assert client.post("/api/v1/auth/login", json=account).status_code == 403


def test_session_expiry_and_disabled_account(client, db, account):
    session = db.scalar(select(UserSession))
    session.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert client.get("/api/v1/me").status_code == 401
    assert client.post("/api/v1/auth/login", json=account).status_code == 200
    user = db.scalar(select(User))
    user.is_active = False
    db.commit()
    assert client.get("/api/v1/me").status_code == 401
    assert client.post("/api/v1/auth/login", json=account).status_code == 401


def test_registration_cannot_assign_admin_role(client):
    body = {"email": "admin@example.com", "password": "long-enough-password", "role": "SuperAdmin"}
    assert client.post("/api/v1/auth/register", json=body).status_code == 422


def test_password_policy_and_email_normalization(client):
    assert (
        client.post("/api/v1/auth/register", json={"email": "bad", "password": "short"}).status_code
        == 422
    )
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "MixedCase@EXAMPLE.COM", "password": "long-enough-password"},
    )
    assert response.status_code == 201
    assert response.json()["email"] == "mixedcase@example.com"
