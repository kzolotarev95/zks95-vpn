from datetime import UTC, datetime, timedelta

import httpx
import pytest
from app.core.encryption import decrypt, encrypt
from app.core.security import utcnow
from app.integrations.vpn import Panel, PanelError, RemoteAccess
from app.models.entities import Order, Subscription, User, VpnAccess, VpnProvider
from app.services.orders import place_order
from app.services.vpn import provision_order, revoke_access, subscription_view
from fastapi import HTTPException
from sqlalchemy import select


def test_3x_ui_access_is_read_from_the_panel_subscription():
    def handler(request: httpx.Request):
        assert request.headers["authorization"] == "Bearer panel-token"
        return httpx.Response(
            200,
            json={
                "success": True,
                "obj": {
                    "client": {
                        "email": "zks-user",
                        "subId": "remote-sub-id",
                        "expiryTime": 1_900_000_000_000,
                        "enable": True,
                    },
                    "usedTraffic": 4096,
                },
            },
        )

    adapter = Panel(
        "3x-ui",
        "https://panel.example",
        {"token": "panel-token"},
        {"subscription_base_url": "https://panel.example/sub", "inbound_ids": [1]},
    )
    adapter.client = httpx.Client(
        base_url="https://panel.example/", transport=httpx.MockTransport(handler)
    )
    with adapter:
        remote = adapter.parse(adapter.lookup("zks-user"))
    assert remote.url == "https://panel.example/sub/remote-sub-id"
    assert remote.used_bytes == 4096
    assert remote.status == "active"
    assert remote.expires_at == datetime.fromtimestamp(1_900_000_000, UTC)
    adapter.client.close()


def test_remnawave_response_keeps_its_real_subscription_url():
    adapter = Panel(
        "remnawave",
        "https://panel.example",
        {"token": "panel-token"},
        {"squad_ids": []},
    )
    remote = adapter.parse(
        {
            "status": "ACTIVE",
            "subscriptionUrl": "https://panel.example/api/sub/abc",
            "expireAt": "2030-01-01T00:00:00Z",
            "userTraffic": {"usedTrafficBytes": 8192},
        }
    )
    assert remote.url == "https://panel.example/api/sub/abc"
    assert remote.status == "active"
    assert remote.used_bytes == 8192
    adapter.client.close()


def test_3x_ui_revoke_preserves_the_full_remote_client():
    stored = {
        "email": "zks-user",
        "id": "uuid",
        "subId": "remote-sub-id",
        "enable": True,
        "password": "panel-generated-secret",
        "expiryTime": 1_900_000_000_000,
    }

    def handler(request):
        import json

        if request.method == "GET":
            return httpx.Response(200, json={"success": True, "obj": {"client": stored}})
        assert json.loads(request.content) == {**stored, "enable": False}
        return httpx.Response(200, json={"success": True})

    adapter = Panel("3x-ui", "https://panel.example", {"token": "panel-token"}, {})
    adapter.client.close()
    adapter.client = httpx.Client(
        base_url="https://panel.example/", transport=httpx.MockTransport(handler)
    )
    with adapter:
        adapter.disable("zks-user")


@pytest.fixture
def vpn_order(db, plan):
    provider = VpnProvider(
        name="Test panel",
        kind="remnawave",
        base_url="https://panel.example",
        credentials_encrypted=encrypt('{"token":"panel-token"}'),
        options={},
    )
    user = User(email="vpn-owner@example.com", password_hash=None)
    db.add_all([provider, user])
    db.flush()
    plan.provider_id = provider.id
    db.commit()
    return place_order(db, user, plan.id, "test-vpn-order-idempotency")


def test_grant_retries_after_lost_reply_without_duplicate_identity(db, vpn_order, monkeypatch):
    identities = []

    class Adapter:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def ensure(self, username, identity, expires_at, devices):
            identities.append((username, identity))
            if len(identities) == 1:
                raise PanelError()
            return RemoteAccess("https://sub.example/real-link", "active", expires_at, 1024)

        def disable(self, username):
            assert username == identities[0][0]

    monkeypatch.setattr("app.services.vpn.panel", lambda _: Adapter())
    with pytest.raises(HTTPException) as error:
        provision_order(db, vpn_order.id, vpn_order.user_id, manual=True)
    assert error.value.status_code == 502
    sub = db.scalar(select(Subscription))
    access = db.get(VpnAccess, sub.id)
    assert access.status == "pending"
    assert subscription_view(db, sub).connection_url is None
    result = provision_order(db, vpn_order.id, vpn_order.user_id, manual=True)
    assert identities[0] == identities[1]
    assert result.connection_url == "https://sub.example/real-link"
    assert "real-link" not in access.connection_encrypted
    assert decrypt(access.connection_encrypted) == result.connection_url
    assert provision_order(db, vpn_order.id, vpn_order.user_id, manual=True).id == sub.id
    assert len(identities) == 2
    assert len(db.scalars(select(Subscription)).all()) == 1
    assert db.get(Order, vpn_order.id).status == "pending"
    revoke_access(db, sub)
    db.commit()
    assert subscription_view(db, sub).connection_url is None
    assert sub.status == "revoked"


def test_unpaid_orders_require_an_explicit_admin_grant(db, vpn_order):
    with pytest.raises(HTTPException) as error:
        provision_order(db, vpn_order.id, vpn_order.user_id)
    assert error.value.status_code == 409
    assert db.scalar(select(Subscription)) is None


def test_expired_subscription_does_not_expose_a_connection(db, vpn_order):
    sub = Subscription(
        user_id=vpn_order.user_id,
        order_id=vpn_order.id,
        plan_name=vpn_order.plan_name,
        device_limit=3,
        status="active",
        starts_at=utcnow() - timedelta(days=2),
        expires_at=utcnow() - timedelta(days=1),
    )
    db.add(sub)
    db.flush()
    db.add(
        VpnAccess(
            subscription_id=sub.id,
            provider_id=vpn_order.provider_id,
            remote_username="expired",
            identity_encrypted=encrypt("{}"),
            connection_encrypted=encrypt("https://sub.example/x"),
            status="active",
        )
    )
    db.commit()
    view = subscription_view(db, sub)
    assert view.status == "expired"
    assert view.connection_url is None
