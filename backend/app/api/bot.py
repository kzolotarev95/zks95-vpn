import secrets
from datetime import timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.encryption import decrypt
from app.core.limiter import rate_limit
from app.core.security import as_utc, token_digest, utcnow
from app.models.entities import (
    AuditLog,
    Order,
    Plan,
    Subscription,
    TelegramAccount,
    TelegramLink,
    TelegramSettings,
    User,
)
from app.schemas.api import OrderOut, PlanOut
from app.services.orders import place_order
from app.services.vpn import refresh_access, subscription_view


def service_auth(x_bot_service_token: str = Header(default="")) -> None:
    expected = get_settings().bot_service_token
    if not expected or not secrets.compare_digest(expected.encode(), x_bot_service_token.encode()):
        raise HTTPException(401, "Service authentication required")


router = APIRouter(
    prefix="/api/v1/internal/bot", tags=["bot internal"], dependencies=[Depends(service_auth)]
)
account_router = APIRouter(prefix="/api/v1/me", tags=["telegram account"])


class TelegramIdentity(BaseModel):
    telegram_id: int = Field(gt=0, le=2**53 - 1)
    username: str | None = Field(default=None, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    link_token: str | None = Field(default=None, max_length=64)


class BotOrder(BaseModel):
    telegram_id: int = Field(gt=0, le=2**53 - 1)
    plan_id: UUID
    idempotency_key: str = Field(min_length=16, max_length=64, pattern=r"^[\w-]+$")


class Heartbeat(BaseModel):
    revision: int
    running: bool
    error: Literal["telegram_unavailable", "telegram_conflict", "telegram_unauthorized"] | None = (
        None
    )


def telegram_user(telegram_id: int, db: Session) -> User:
    identity = db.get(TelegramAccount, telegram_id)
    user = db.get(User, identity.user_id) if identity else None
    if not user:
        raise HTTPException(404, "Нажмите /start, чтобы открыть аккаунт")
    if not user.is_active:
        raise HTTPException(403, "Аккаунт заблокирован. Обратитесь в поддержку")
    return user


@router.get("/config")
def config(db: Session = Depends(get_db)):
    row = db.get(TelegramSettings, 1)
    return {
        "enabled": bool(row and row.enabled),
        "revision": row.revision if row else 0,
        "token": decrypt(row.token_encrypted)
        if row and row.enabled and row.token_encrypted
        else None,
        "public_url": get_settings().public_url,
        "support_username": row.support_username if row else None,
    }


@router.post("/heartbeat", status_code=204)
def heartbeat(body: Heartbeat, db: Session = Depends(get_db)):
    row = db.get(TelegramSettings, 1)
    if row and row.revision == body.revision:
        row.last_seen_at = utcnow() if body.running else None
        row.last_error = body.error
        db.commit()


@router.post("/account")
def account(body: TelegramIdentity, db: Session = Depends(get_db)):
    identity = db.get(TelegramAccount, body.telegram_id)
    if body.link_token:
        link = db.scalar(
            select(TelegramLink)
            .where(TelegramLink.token_hash == token_digest(body.link_token))
            .with_for_update()
        )
        if not link or as_utc(link.expires_at) <= utcnow():
            raise HTTPException(422, "Ссылка устарела. Создайте новую в личном кабинете")
        if identity and identity.user_id != link.user_id:
            raise HTTPException(409, "Этот Telegram уже привязан к другому аккаунту")
        other = db.scalar(select(TelegramAccount).where(TelegramAccount.user_id == link.user_id))
        if other and other.telegram_id != body.telegram_id:
            raise HTTPException(409, "К аккаунту уже привязан другой Telegram")
        user = db.get(User, link.user_id)
        if not user or not user.is_active:
            raise HTTPException(403, "Аккаунт недоступен")
        if not identity:
            identity = TelegramAccount(
                telegram_id=body.telegram_id,
                user_id=link.user_id,
                display_name=body.display_name,
                username=body.username,
            )
            db.add(identity)
        db.delete(link)
        db.add(AuditLog(actor_id=user.id, action="telegram.link", target_id=str(body.telegram_id)))
    elif not identity:
        user = User(email=None, password_hash=None)
        db.add(user)
        db.flush()
        identity = TelegramAccount(
            telegram_id=body.telegram_id,
            user_id=user.id,
            display_name=body.display_name,
            username=body.username,
        )
        db.add(identity)
        db.add(
            AuditLog(actor_id=user.id, action="telegram.register", target_id=str(body.telegram_id))
        )
    else:
        user = telegram_user(body.telegram_id, db)
    identity.username = body.username
    identity.display_name = body.display_name
    db.commit()
    return {"user_id": str(user.id), "email": user.email}


@router.get("/users/{telegram_id}/snapshot")
def snapshot(telegram_id: int, db: Session = Depends(get_db)):
    user = telegram_user(telegram_id, db)
    subs = []
    for row in db.scalars(
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .order_by(Subscription.expires_at.desc())
        .limit(100)
    ):
        sub = subscription_view(db, row)
        subs.append(sub.model_dump())
    return {
        "user_id": str(user.id),
        "email": user.email,
        "subscriptions": subs,
        "orders": [
            OrderOut.model_validate(row).model_dump()
            for row in db.scalars(
                select(Order)
                .where(Order.user_id == user.id)
                .order_by(Order.created_at.desc())
                .limit(20)
            )
        ],
        "plans": [
            PlanOut.model_validate(row).model_dump()
            for row in db.scalars(
                select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.price_minor)
            )
        ],
    }


@router.post("/users/{telegram_id}/refresh")
def refresh(telegram_id: int, request: Request, db: Session = Depends(get_db)):
    rate_limit(request, f"vpn-refresh-{telegram_id}", 10, 60)
    user = telegram_user(telegram_id, db)
    for sub in db.scalars(
        select(Subscription)
        .where(
            Subscription.user_id == user.id,
            Subscription.status == "active",
        )
        .limit(20)
    ).all():
        refresh_access(db, sub)
    return snapshot(telegram_id, db)


@router.post("/orders", response_model=OrderOut, status_code=201)
def order(body: BotOrder, request: Request, db: Session = Depends(get_db)):
    rate_limit(request, f"bot-orders-{body.telegram_id}", 10, 60)
    return place_order(db, telegram_user(body.telegram_id, db), body.plan_id, body.idempotency_key)


@account_router.get("/telegram")
def linked(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    identity = db.scalar(select(TelegramAccount).where(TelegramAccount.user_id == user.id))
    settings = db.get(TelegramSettings, 1)
    return {
        "linked": bool(identity),
        "username": identity.username if identity else None,
        "bot_username": settings.username if settings and settings.enabled else None,
    }


@account_router.post("/telegram-link")
def link(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rate_limit(request, "telegram-link", 10, 60)
    settings = db.get(TelegramSettings, 1)
    if not settings or not settings.enabled or not settings.username:
        raise HTTPException(409, "Telegram-бот ещё не подключён")
    db.execute(delete(TelegramLink).where(TelegramLink.user_id == user.id))
    token = secrets.token_urlsafe(24)
    db.add(
        TelegramLink(
            token_hash=token_digest(token),
            user_id=user.id,
            expires_at=utcnow() + timedelta(minutes=5),
        )
    )
    db.commit()
    return {"url": f"https://t.me/{settings.username}?start=link_{token}", "expires_in": 300}
