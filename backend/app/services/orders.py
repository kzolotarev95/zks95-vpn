from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import AuditLog, Order, Plan, User


def place_order(db: Session, user: User, plan_id: UUID, idempotency_key: str) -> Order:
    existing = db.scalar(
        select(Order).where(Order.user_id == user.id, Order.idempotency_key == idempotency_key)
    )
    if existing:
        if existing.plan_id != plan_id:
            raise HTTPException(409, "Ключ уже использован для другого тарифа")
        return existing
    plan = db.scalar(select(Plan).where(Plan.id == plan_id, Plan.is_active.is_(True)))
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
        if existing and existing.plan_id == plan_id:
            return existing
        raise HTTPException(409, "Конфликт создания заказа") from exc
    return order
