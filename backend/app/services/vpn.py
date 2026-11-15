import json
import secrets
import uuid
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.encryption import decrypt, encrypt
from app.core.security import as_utc, utcnow
from app.integrations.vpn import Panel, PanelError, RemoteAccess
from app.models.entities import AuditLog, Order, Plan, Subscription, User, VpnAccess, VpnProvider
from app.schemas.api import SubscriptionOut


def panel(provider: VpnProvider) -> Panel:
    return Panel(
        provider.kind,
        provider.base_url,
        json.loads(decrypt(provider.credentials_encrypted)),
        provider.options,
    )


def save_remote(access: VpnAccess, remote: RemoteAccess, sub: Subscription):
    from urllib.parse import urlsplit

    if remote.url:
        parsed = urlsplit(remote.url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise PanelError("Панель вернула некорректную ссылку подписки")
    access.status = remote.status
    access.used_bytes = remote.used_bytes
    access.connection_encrypted = encrypt(remote.url) if remote.url else None
    access.synced_at = utcnow()
    if remote.expires_at:
        sub.expires_at = remote.expires_at


def provision_order(db: Session, order_id: uuid.UUID, actor_id: uuid.UUID, *, manual=False):
    """One durable identity per order, reusable after lost HTTP replies or process restarts."""
    order = db.scalar(select(Order).where(Order.id == order_id).with_for_update())
    if not order:
        raise HTTPException(404, "Заказ не найден")
    if order.status != "paid" and not (manual and order.status == "pending"):
        raise HTTPException(409, "Заказ не оплачен или отменён")
    user = db.get(User, order.user_id)
    if not user or not user.is_active:
        raise HTTPException(409, "Пользователь заблокирован")
    sub = db.scalar(select(Subscription).where(Subscription.order_id == order.id))
    if not sub:
        plan = db.get(Plan, order.plan_id)
        provider_id = order.provider_id or (plan.provider_id if plan else None)
        provider = db.get(VpnProvider, provider_id) if provider_id else None
        if not provider or not provider.is_active:
            raise HTTPException(409, "Сначала подключите панель и назначьте её тарифу")
        sub = Subscription(
            user_id=order.user_id,
            order_id=order.id,
            plan_name=order.plan_name,
            device_limit=order.device_limit,
            starts_at=utcnow(),
            expires_at=utcnow() + timedelta(days=order.duration_days),
            status="active",
        )
        db.add(sub)
        db.flush()
        db.add(
            VpnAccess(
                subscription_id=sub.id,
                provider_id=provider.id,
                remote_username="zks" + sub.id.hex,
                identity_encrypted=encrypt(
                    json.dumps(
                        {
                            "id": str(uuid.uuid4()),
                            "password": secrets.token_urlsafe(24),
                            "sub_id": secrets.token_urlsafe(24),
                        }
                    )
                ),
                status="pending",
            )
        )
        db.add(
            AuditLog(
                actor_id=actor_id,
                action="vpn.manual_grant_requested" if manual else "vpn.paid_order_requested",
                target_id=str(order.id),
            )
        )
        # Persist identity before external effects; an unsuccessful call is retryable.
        db.commit()
    if sub.status != "active":
        raise HTTPException(409, "Подписка отозвана или истекла")
    access = db.scalar(
        select(VpnAccess).where(VpnAccess.subscription_id == sub.id).with_for_update()
    )
    if not access:
        raise HTTPException(409, "Для старой подписки нет привязки к панели")
    if access.status != "pending":
        return subscription_view(db, sub)
    provider = db.get(VpnProvider, access.provider_id)
    if not provider or not provider.is_active:
        raise HTTPException(409, "Панель выключена")
    try:
        with panel(provider) as adapter:
            remote = adapter.ensure(
                access.remote_username,
                json.loads(decrypt(access.identity_encrypted)),
                as_utc(sub.expires_at),
                sub.device_limit,
            )
        save_remote(access, remote, sub)
    except PanelError as exc:
        db.rollback()
        raise HTTPException(502, str(exc)) from None
    db.add(AuditLog(actor_id=actor_id, action="vpn.provision", target_id=str(sub.id)))
    db.commit()
    return subscription_view(db, sub)


def refresh_access(db: Session, sub: Subscription):
    access = db.get(VpnAccess, sub.id)
    if not access or access.status == "pending" or sub.status == "revoked":
        return subscription_view(db, sub)
    provider = db.get(VpnProvider, access.provider_id)
    if not provider or not provider.is_active:
        raise HTTPException(409, "Панель VPN отключена")
    try:
        with panel(provider) as adapter:
            remote = adapter.lookup(access.remote_username)
            if remote:
                save_remote(access, adapter.parse(remote), sub)
            else:
                access.status, access.connection_encrypted = "missing", None
                access.synced_at = utcnow()
        db.commit()
    except PanelError as exc:
        db.rollback()
        raise HTTPException(502, str(exc)) from None
    return subscription_view(db, sub)


def revoke_access(db: Session, sub: Subscription):
    access = db.get(VpnAccess, sub.id)
    if access:
        provider = db.get(VpnProvider, access.provider_id)
        if not provider:
            raise HTTPException(409, "Панель VPN удалена")
        try:
            with panel(provider) as adapter:
                adapter.disable(access.remote_username)
        except PanelError as exc:
            raise HTTPException(502, str(exc)) from None
        access.status, access.connection_encrypted = "disabled", None
        access.synced_at = utcnow()
    sub.status = "revoked"


def subscription_view(db: Session, sub: Subscription) -> SubscriptionOut:
    result = SubscriptionOut.model_validate(sub)
    if sub.status == "active" and as_utc(sub.expires_at) <= utcnow():
        result.status = "expired"
    access = db.get(VpnAccess, sub.id)
    if access:
        provider = db.get(VpnProvider, access.provider_id)
        result.provider_name = provider.name if provider else None
        result.vpn_status = access.status
        result.used_bytes = access.used_bytes
        if result.status == "active" and access.status == "active" and access.connection_encrypted:
            result.connection_url = decrypt(access.connection_encrypted)
    return result
