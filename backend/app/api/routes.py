import secrets
from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from redis.exceptions import RedisError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import COOKIE_NAME, get_current_session, get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.limiter import get_redis, rate_limit
from app.core.security import (
    as_utc,
    dummy_password_hash,
    hash_password,
    token_digest,
    utcnow,
    verify_password,
)
from app.models.entities import AuditLog, Order, Plan, Subscription, User, UserSession
from app.schemas.api import (
    CreateOrder,
    Credentials,
    OrderOut,
    PlanOut,
    SubscriptionOut,
    UserOut,
)

router = APIRouter(prefix="/api/v1")


@router.get("/health/live", tags=["health"])
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", tags=["health"])
def ready(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1 FROM alembic_version"))
        get_redis().ping()
    except (SQLAlchemyError, RedisError, OSError) as exc:
        raise HTTPException(503, "Dependencies unavailable") from exc
    return {"status": "ready"}


def start_session(db: Session, user: User, response: Response) -> None:
    settings = get_settings()
    token = secrets.token_urlsafe(48)
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=token_digest(token),
            expires_at=utcnow() + timedelta(hours=settings.session_hours),
        )
    )
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.session_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/auth/register", response_model=UserOut, status_code=201, tags=["auth"])
def register(
    body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)
) -> User:
    rate_limit(request, "register", 5, 3600)
    user = User(email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    try:
        db.flush()
        start_session(db, user, response)
        db.add(AuditLog(actor_id=user.id, action="auth.register", target_id=str(user.id)))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Не удалось зарегистрировать аккаунт с этим адресом") from exc
    return user


@router.post("/auth/login", response_model=UserOut, tags=["auth"])
def login(
    body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)
) -> User:
    rate_limit(request, "login", 10, 300)
    user = db.scalar(select(User).where(User.email == body.email))
    verified = verify_password(body.password, user.password_hash if user else dummy_password_hash)
    if not user or not verified or not user.is_active:
        raise HTTPException(401, "Неверный адрес или пароль")
    start_session(db, user, response)
    db.add(AuditLog(actor_id=user.id, action="auth.login", target_id=str(user.id)))
    db.commit()
    return user


@router.post("/auth/logout", status_code=204, tags=["auth"])
def logout(
    response: Response,
    session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> None:
    db.delete(session)
    db.commit()
    response.delete_cookie(
        COOKIE_NAME, path="/", secure=get_settings().cookie_secure, httponly=True, samesite="lax"
    )


@router.get("/me", response_model=UserOut, tags=["account"])
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.get("/plans", response_model=list[PlanOut], tags=["catalog"])
def plans(db: Session = Depends(get_db)) -> list[Plan]:
    return list(db.scalars(select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.price_minor)))


@router.post("/orders", response_model=OrderOut, status_code=201, tags=["orders"])
def create_order(
    body: CreateOrder,
    request: Request,
    idempotency_key: Annotated[str, Header(min_length=16, max_length=64, pattern=r"^[\w-]+$")],
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Order:
    rate_limit(request, "orders", 30, 60)
    existing = db.scalar(
        select(Order).where(Order.user_id == user.id, Order.idempotency_key == idempotency_key)
    )
    if existing:
        if existing.plan_id != body.plan_id:
            raise HTTPException(409, "Ключ уже использован для другого тарифа")
        return existing
    plan = db.scalar(select(Plan).where(Plan.id == body.plan_id, Plan.is_active.is_(True)))
    if not plan:
        raise HTTPException(404, "Тариф недоступен")
    order = Order(
        user_id=user.id,
        plan_id=plan.id,
        idempotency_key=idempotency_key,
        amount_minor=plan.price_minor,
        currency=plan.currency,
        plan_name=plan.name,
        duration_days=plan.duration_days,
        device_limit=plan.device_limit,
        status="pending",
    )
    db.add(order)
    try:
        db.flush()
        db.add(AuditLog(actor_id=user.id, action="order.create", target_id=str(order.id)))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        existing = db.scalar(
            select(Order).where(Order.user_id == user.id, Order.idempotency_key == idempotency_key)
        )
        if existing and existing.plan_id == body.plan_id:
            return existing
        raise HTTPException(409, "Конфликт создания заказа") from exc
    return order


@router.get("/orders", response_model=list[OrderOut], tags=["orders"])
def orders(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Order]:
    return list(
        db.scalars(
            select(Order)
            .where(Order.user_id == user.id)
            .order_by(Order.created_at.desc())
            .limit(100)
        )
    )


@router.get("/orders/{order_id}", response_model=OrderOut, tags=["orders"])
def get_order(
    order_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Order:
    order = db.scalar(select(Order).where(Order.id == order_id, Order.user_id == user.id))
    if not order:
        raise HTTPException(404, "Заказ не найден")
    return order


@router.get("/subscriptions", response_model=list[SubscriptionOut], tags=["account"])
def subscriptions(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[SubscriptionOut]:
    rows = db.scalars(
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .order_by(Subscription.expires_at.desc())
        .limit(100)
    )
    result = []
    for row in rows:
        item = SubscriptionOut.model_validate(row)
        if item.status == "active" and as_utc(row.expires_at) <= utcnow():
            item.status = "expired"
        result.append(item)
    return result
