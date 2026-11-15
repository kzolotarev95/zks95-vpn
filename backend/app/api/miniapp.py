import secrets
from datetime import timedelta
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_telegram_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.encryption import decrypt
from app.core.security import token_digest, utcnow
from app.integrations.telegram_webapp import verify_init_data
from app.models.entities import (
    AuditLog,
    Order,
    Plan,
    Subscription,
    TelegramAccount,
    TelegramSettings,
    User,
    UserSession,
)
from app.schemas.api import CreateOrder, OrderOut, PlanOut, UserOut
from app.services.orders import place_order
from app.services.vpn import subscription_view

router = APIRouter(prefix="/api/v1/miniapp", tags=["miniapp"])
MINIAPP_COOKIE = "zks95_telegram"


class MiniAppAuth(BaseModel):
    init_data: str = Field(min_length=1, max_length=4096)


def telegram_token(db: Session) -> str:
    row = db.get(TelegramSettings, 1)
    if not row or not row.enabled or not row.token_encrypted:
        raise HTTPException(503, "Telegram-бот ещё не настроен")
    return decrypt(row.token_encrypted)


@router.post("/auth", response_model=UserOut)
def auth(body: MiniAppAuth, response: Response, db: Session = Depends(get_db)) -> User:
    data = verify_init_data(body.init_data, telegram_token(db))
    telegram_id = int(data["id"])
    account = db.get(TelegramAccount, telegram_id)
    user = db.get(User, account.user_id) if account else None
    if user and not user.is_active:
        raise HTTPException(403, "Аккаунт заблокирован")
    display_name = " ".join(str(data.get(key, "")) for key in ("first_name", "last_name")).strip()[
        :128
    ]
    if not user:
        user = User(email=None, password_hash=None)
        db.add(user)
        db.flush()
        db.add(
            TelegramAccount(
                telegram_id=telegram_id,
                user_id=user.id,
                username=data.get("username"),
                display_name=display_name or str(telegram_id),
            )
        )
        db.add(
            AuditLog(
                actor_id=user.id, action="telegram.miniapp_register", target_id=str(telegram_id)
            )
        )
    else:
        account.username = data.get("username")
        account.display_name = display_name or account.display_name
    token = secrets.token_urlsafe(48)
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=token_digest(token),
            purpose="telegram",
            expires_at=utcnow() + timedelta(hours=get_settings().session_hours),
        )
    )
    db.commit()
    response.set_cookie(
        MINIAPP_COOKIE,
        token,
        max_age=get_settings().session_hours * 3600,
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="lax",
        path="/",
    )
    return user


@router.get("/bootstrap")
def bootstrap(user: User = Depends(get_current_telegram_user), db: Session = Depends(get_db)):
    return {
        "user": UserOut.model_validate(user).model_dump(),
        "support_username": (
            db.get(TelegramSettings, 1).support_username if db.get(TelegramSettings, 1) else None
        ),
        "plans": [
            PlanOut.model_validate(row).model_dump()
            for row in db.scalars(
                select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.price_minor)
            )
        ],
        "orders": [
            OrderOut.model_validate(row).model_dump()
            for row in db.scalars(
                select(Order)
                .where(Order.user_id == user.id)
                .order_by(Order.created_at.desc())
                .limit(50)
            )
        ],
        "subscriptions": [
            subscription_view(db, row).model_dump()
            for row in db.scalars(
                select(Subscription)
                .where(Subscription.user_id == user.id)
                .order_by(Subscription.expires_at.desc())
                .limit(50)
            )
        ],
    }


@router.post("/orders", response_model=OrderOut, status_code=201)
def create_order(
    body: CreateOrder,
    idempotency_key: str = Header(min_length=16, max_length=64, alias="Idempotency-Key"),
    user: User = Depends(get_current_telegram_user),
    db: Session = Depends(get_db),
):
    return place_order(db, user, body.plan_id, idempotency_key)


@router.post("/orders/{order_id}/stars-invoice")
def stars_invoice(
    order_id: UUID,
    user: User = Depends(get_current_telegram_user),
    db: Session = Depends(get_db),
):
    order = db.scalar(select(Order).where(Order.id == order_id, Order.user_id == user.id))
    if not order or not order.stars_price:
        raise HTTPException(409, "Для тарифа не настроена цена Telegram Stars")
    token = telegram_token(db)
    payload = {
        "title": order.plan_name[:32],
        "description": f"ZKS95 VPN · {order.duration_days} дней",
        "payload": f"zks95:{order.id}",
        "provider_token": "",
        "currency": "XTR",
        "prices": [{"label": order.plan_name[:32], "amount": order.stars_price}],
    }
    try:
        with httpx.Client(timeout=15) as client:
            result = client.post(
                f"https://api.telegram.org/bot{token}/createInvoiceLink", json=payload
            ).json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(503, "Telegram временно недоступен") from exc
    if not result.get("ok") or not result.get("result"):
        raise HTTPException(502, "Telegram не создал ссылку оплаты")
    return {"invoice_url": result["result"], "payload": payload["payload"]}
