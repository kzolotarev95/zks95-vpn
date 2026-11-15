from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.entities import Order, Payment, User
from app.schemas.api import PaymentOut
from app.services.billing import BillingError, confirm_yookassa_payment, create_yookassa_payment

router = APIRouter(prefix="/api/v1", tags=["billing"])


@router.get("/billing/status")
def billing_status(db: Session = Depends(get_db)) -> dict[str, bool]:
    from app.services.billing import billing_config

    shop, secret, _ = billing_config(db)
    return {"yookassa_enabled": bool(shop and secret)}


@router.post("/orders/{order_id}/payments/yookassa", response_model=PaymentOut)
def create_payment(
    order_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Payment:
    order = db.scalar(select(Order).where(Order.id == order_id, Order.user_id == user.id))
    if not order:
        raise HTTPException(404, "Заказ не найден")
    try:
        return create_yookassa_payment(db, order, user)
    except BillingError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/orders/{order_id}/payment", response_model=PaymentOut | None)
def payment_status(
    order_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Payment | None:
    order = db.scalar(select(Order).where(Order.id == order_id, Order.user_id == user.id))
    if not order:
        raise HTTPException(404, "Заказ не найден")
    return db.scalar(
        select(Payment).where(Payment.order_id == order.id).order_by(Payment.created_at.desc())
    )


@router.post("/payments/yookassa/webhook", status_code=204)
async def yookassa_webhook(request: Request, db: Session = Depends(get_db)) -> None:
    # YooKassa webhooks are only a wake-up signal. The billing service performs
    # an authenticated GET before changing the order state.
    import json

    try:
        payload = await request.json()
        external_id = str((payload.get("object") or {}).get("id") or "")
        if not external_id:
            raise BillingError("Нет идентификатора платежа")
        confirm_yookassa_payment(db, external_id, payload)
    except (BillingError, HTTPException, ValueError, TypeError, json.JSONDecodeError):
        # Responding with 204 avoids webhook retry storms for unknown payments.
        return
