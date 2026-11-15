import secrets
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.encryption import encrypt
from app.core.limiter import rate_limit
from app.core.security import as_utc, dummy_password_hash, token_digest, utcnow, verify_password
from app.integrations.telegram import validate_bot_token
from app.models.entities import (
    AdminUser,
    AuditLog,
    Order,
    Plan,
    Role,
    Subscription,
    TelegramAccount,
    TelegramSettings,
    User,
    UserSession,
)
from app.schemas.admin import (
    AdminCredentials,
    AdminProfile,
    AdminUserOut,
    AuditOut,
    PlanWrite,
    TelegramStatus,
    TelegramWrite,
    UserState,
)
from app.schemas.api import OrderOut, PlanOut, SubscriptionOut
from app.services.admin import (
    ADMIN_COOKIE,
    PERMISSIONS,
    AdminContext,
    get_admin,
    permission,
    verify_totp,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def profile(admin: AdminContext) -> AdminProfile:
    return AdminProfile(
        **AdminProfile.model_validate(
            {
                "id": admin.user.id,
                "email": admin.user.email,
                "created_at": admin.user.created_at,
                "role": admin.role,
                "permissions": sorted(PERMISSIONS[admin.role]),
            }
        ).model_dump()
    )


@router.post("/login", response_model=AdminProfile)
def login(
    body: AdminCredentials, request: Request, response: Response, db: Session = Depends(get_db)
) -> AdminProfile:
    rate_limit(request, "admin-login", 10, 300)
    user = db.scalar(select(User).where(User.email == body.email))
    valid = verify_password(
        body.password, (user.password_hash if user else None) or dummy_password_hash
    )
    member = (
        db.scalar(select(AdminUser).where(AdminUser.user_id == user.id).with_for_update())
        if user
        else None
    )
    if not valid or not user or not user.is_active or not member:
        raise HTTPException(401, "Неверный email, пароль или код 2FA")
    if not verify_totp(member, body.otp, db):
        raise HTTPException(401, "Неверный email, пароль или код 2FA")
    role = db.get(Role, member.role_id)
    if not role or role.name not in PERMISSIONS:
        raise HTTPException(403, "Роль не настроена")
    token = secrets.token_urlsafe(48)
    session = UserSession(
        user_id=user.id,
        token_hash=token_digest(token),
        purpose="admin",
        expires_at=utcnow() + timedelta(minutes=30),
    )
    db.add(session)
    db.add(AuditLog(actor_id=user.id, action="admin.login", target_id=str(user.id)))
    db.commit()
    response.set_cookie(
        ADMIN_COOKIE,
        token,
        max_age=1800,
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="strict",
        path="/api/v1/admin",
    )
    return profile(AdminContext(user, member, session, role.name))


@router.post("/logout", status_code=204)
def logout(
    response: Response, admin: AdminContext = Depends(get_admin), db: Session = Depends(get_db)
) -> None:
    db.delete(admin.session)
    db.commit()
    response.delete_cookie(
        ADMIN_COOKIE,
        path="/api/v1/admin",
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="strict",
    )


@router.get("/me", response_model=AdminProfile)
def me(admin: AdminContext = Depends(get_admin)) -> AdminProfile:
    return profile(admin)


@router.get("/overview")
def overview(
    admin: AdminContext = Depends(permission("overview")), db: Session = Depends(get_db)
) -> dict:
    return {
        "users": db.scalar(select(func.count()).select_from(User)),
        "telegram_users": db.scalar(select(func.count()).select_from(TelegramAccount)),
        "orders": db.scalar(select(func.count()).select_from(Order)),
        "pending_orders": db.scalar(
            select(func.count()).select_from(Order).where(Order.status == "pending")
        ),
        "active_subscriptions": db.scalar(
            select(func.count())
            .select_from(Subscription)
            .where(Subscription.status == "active", Subscription.expires_at > utcnow())
        ),
        "revenue_minor": db.scalar(
            select(func.coalesce(func.sum(Order.amount_minor), 0)).where(Order.status == "paid")
        ),
        "currency": "RUB",
    }


@router.get("/users", response_model=list[AdminUserOut])
def users(
    q: str = Query(default="", max_length=254),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    admin: AdminContext = Depends(permission("users")),
    db: Session = Depends(get_db),
):
    query = (
        select(User, TelegramAccount, Role.name)
        .outerjoin(TelegramAccount, TelegramAccount.user_id == User.id)
        .outerjoin(AdminUser, AdminUser.user_id == User.id)
        .outerjoin(Role, Role.id == AdminUser.role_id)
    )
    if q:
        conditions = [User.email.ilike(f"%{q}%"), TelegramAccount.username.ilike(f"%{q}%")]
        if q.isascii() and q.isdigit() and len(q) < 19:
            conditions.append(TelegramAccount.telegram_id == int(q))
        query = query.where(or_(*conditions))
    result = []
    for user, telegram, role in db.execute(
        query.order_by(User.created_at.desc()).offset(offset).limit(limit)
    ):
        result.append(
            AdminUserOut(
                id=user.id,
                email=user.email,
                created_at=user.created_at,
                is_active=user.is_active,
                telegram_id=telegram.telegram_id if telegram else None,
                telegram_username=telegram.username if telegram else None,
                display_name=telegram.display_name if telegram else None,
                role=role,
            )
        )
    return result


@router.patch("/users/{user_id}", response_model=AdminUserOut)
def user_state(
    user_id: UUID,
    body: UserState,
    admin: AdminContext = Depends(permission("users:write")),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    if user.id == admin.user.id:
        raise HTTPException(409, "Нельзя блокировать собственный аккаунт")
    if db.get(AdminUser, user.id) and admin.role != "SuperAdmin":
        raise HTTPException(403, "Только SuperAdmin может изменять аккаунты администраторов")
    user.is_active = body.is_active
    if not body.is_active:
        db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db.add(
        AuditLog(
            actor_id=admin.user.id,
            action="user.unblock" if body.is_active else "user.block",
            target_id=str(user.id),
        )
    )
    db.commit()
    return AdminUserOut.model_validate(user)


@router.get("/plans")
def plans(admin: AdminContext = Depends(permission("plans")), db: Session = Depends(get_db)):
    return [
        {**PlanOut.model_validate(plan).model_dump(), "is_active": plan.is_active}
        for plan in db.scalars(select(Plan).order_by(Plan.price_minor))
    ]


@router.post("/plans", status_code=201)
def create_plan(
    body: PlanWrite,
    admin: AdminContext = Depends(permission("plans:write")),
    db: Session = Depends(get_db),
):
    plan = Plan(**body.model_dump(), currency="RUB")
    db.add(plan)
    try:
        db.flush()
        db.add(AuditLog(actor_id=admin.user.id, action="plan.create", target_id=str(plan.id)))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Код тарифа уже занят") from None
    return {**PlanOut.model_validate(plan).model_dump(), "is_active": plan.is_active}


@router.put("/plans/{plan_id}")
def update_plan(
    plan_id: UUID,
    body: PlanWrite,
    admin: AdminContext = Depends(permission("plans:write")),
    db: Session = Depends(get_db),
):
    plan = db.get(Plan, plan_id)
    if not plan:
        raise HTTPException(404, "Тариф не найден")
    for key, value in body.model_dump().items():
        setattr(plan, key, value)
    db.add(AuditLog(actor_id=admin.user.id, action="plan.update", target_id=str(plan.id)))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Код тарифа уже занят") from None
    return {**PlanOut.model_validate(plan).model_dump(), "is_active": plan.is_active}


@router.get("/orders")
def orders(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    admin: AdminContext = Depends(permission("orders")),
    db: Session = Depends(get_db),
):
    return [
        {**OrderOut.model_validate(order).model_dump(), "user_id": user.id, "email": user.email}
        for order, user in db.execute(
            select(Order, User)
            .join(User, User.id == Order.user_id)
            .order_by(Order.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ]


@router.get("/subscriptions")
def subscriptions(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    admin: AdminContext = Depends(permission("subscriptions")),
    db: Session = Depends(get_db),
):
    result = []
    for sub, user in db.execute(
        select(Subscription, User)
        .join(User, User.id == Subscription.user_id)
        .order_by(Subscription.expires_at.desc())
        .offset(offset)
        .limit(limit)
    ):
        data = SubscriptionOut.model_validate(sub).model_dump()
        if sub.status == "active" and as_utc(sub.expires_at) <= utcnow():
            data["status"] = "expired"
        result.append({**data, "user_id": user.id, "email": user.email})
    return result


@router.post("/subscriptions/{subscription_id}/revoke", status_code=204)
def revoke(
    subscription_id: UUID,
    admin: AdminContext = Depends(permission("subscriptions:write")),
    db: Session = Depends(get_db),
):
    sub = db.get(Subscription, subscription_id)
    if not sub:
        raise HTTPException(404, "Подписка не найдена")
    sub.status = "revoked"
    db.add(AuditLog(actor_id=admin.user.id, action="subscription.revoke", target_id=str(sub.id)))
    db.commit()


@router.get("/audit", response_model=list[AuditOut])
def audit(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    admin: AdminContext = Depends(permission("audit")),
    db: Session = Depends(get_db),
):
    return list(
        db.scalars(
            select(AuditLog).order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
        )
    )


def bot_status(row: TelegramSettings | None) -> TelegramStatus:
    if not row:
        return TelegramStatus()
    connected = bool(
        row.enabled
        and row.last_seen_at
        and as_utc(row.last_seen_at) > utcnow() - timedelta(seconds=45)
        and not row.last_error
    )
    return TelegramStatus(
        configured=bool(row.token_encrypted),
        enabled=row.enabled,
        username=row.username,
        bot_id=row.bot_id,
        connected=connected,
        support_username=row.support_username,
        last_seen_at=row.last_seen_at,
        last_error=row.last_error,
    )


@router.get("/telegram", response_model=TelegramStatus)
def telegram(admin: AdminContext = Depends(permission("telegram")), db: Session = Depends(get_db)):
    return bot_status(db.get(TelegramSettings, 1))


@router.put("/telegram", response_model=TelegramStatus)
def update_telegram(
    body: TelegramWrite,
    admin: AdminContext = Depends(permission("telegram")),
    db: Session = Depends(get_db),
):
    row = db.get(TelegramSettings, 1)
    if not row:
        row = TelegramSettings(id=1, enabled=False, revision=0)
        db.add(row)
    if body.token and body.token.get_secret_value():
        data = validate_bot_token(body.token.get_secret_value())
        row.token_encrypted = encrypt(body.token.get_secret_value())
        row.username, row.bot_id = data.get("username"), data["id"]
    if body.enabled and not row.token_encrypted:
        raise HTTPException(422, "Сначала укажите токен BotFather")
    row.enabled = body.enabled
    row.support_username = body.support_username
    row.revision += 1
    row.last_seen_at = None
    row.last_error = None
    db.add(AuditLog(actor_id=admin.user.id, action="telegram.configure", target_id="1"))
    db.commit()
    return bot_status(row)
