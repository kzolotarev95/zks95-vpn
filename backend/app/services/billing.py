"""Payment provider integration and durable payment state transitions."""

from decimal import Decimal
from typing import Any

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.encryption import decrypt
from app.core.security import utcnow
from app.models.entities import BillingSettings, Order, Payment, PaymentEvent, User
from app.services.vpn import provision_order


class BillingError(Exception):
    """A provider error safe to show to an end user."""


def billing_config(db: Session) -> tuple[str, str, bool]:
    settings = get_settings()
    row = db.get(BillingSettings, 1)
    shop_id = row.yookassa_shop_id if row and row.yookassa_shop_id else settings.yookassa_shop_id
    encrypted = row.yookassa_secret_encrypted if row else None
    secret = decrypt(encrypted) if encrypted else settings.yookassa_secret_key
    receipt = row.yookassa_receipt_enabled if row else settings.yookassa_receipt_enabled
    return shop_id.strip(), secret.strip(), bool(receipt)


def _amount(value: int, currency: str = "RUB") -> dict[str, str]:
    return {"value": f"{Decimal(value) / Decimal(100):.2f}", "currency": currency}


class YookassaClient:
    base_url = "https://api.yookassa.ru/v3"

    def __init__(self, shop_id: str, secret: str):
        if not shop_id or not secret:
            raise BillingError("Оплата ЮKassa ещё не настроена администратором")
        self.auth = (shop_id, secret)

    def request(
        self, method: str, path: str, *, payload: dict | None = None, key: str | None = None
    ):
        headers = {"Accept": "application/json"}
        if key:
            headers["Idempotence-Key"] = key
        try:
            with httpx.Client(timeout=15, follow_redirects=False) as client:
                response = client.request(
                    method,
                    self.base_url + path,
                    auth=self.auth,
                    headers=headers,
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise BillingError("Платёжный сервис временно недоступен") from exc
        if response.status_code >= 400:
            raise BillingError("ЮKassa отклонила запрос платежа")
        try:
            return response.json()
        except ValueError as exc:
            raise BillingError("ЮKassa вернула некорректный ответ") from exc

    def create(self, order: Order, user: User, *, receipt: bool = False) -> dict:
        settings = get_settings()
        payload: dict[str, Any] = {
            "amount": _amount(order.amount_minor, order.currency),
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": f"{settings.public_url.rstrip('/')}/dashboard?payment={order.id}",
            },
            "description": f"{order.plan_name} — ZKS95 VPN",
            "metadata": {"order_id": str(order.id)},
        }
        if receipt:
            if not user.email:
                raise BillingError("Для фискального чека сначала добавьте email в аккаунте")
            payload["receipt"] = {
                "customer": {"email": user.email},
                "items": [
                    {
                        "description": order.plan_name[:128],
                        "quantity": "1.00",
                        "amount": _amount(order.amount_minor, order.currency),
                        "vat_code": settings.yookassa_vat_code,
                        "payment_mode": "full_payment",
                        "payment_subject": "service",
                    }
                ],
            }
        return self.request("POST", "/payments", payload=payload, key=f"zks95-order-{order.id}")

    def get(self, external_id: str) -> dict:
        return self.request("GET", f"/payments/{external_id}")

    def refund(self, payment: Payment, amount_minor: int | None = None) -> dict:
        payload = {
            "payment_id": payment.external_id,
            "amount": _amount(amount_minor or payment.amount_minor, payment.currency),
        }
        return self.request(
            "POST",
            "/refunds",
            payload=payload,
            key=f"zks95-refund-{payment.id}",
        )


def create_yookassa_payment(db: Session, order: Order, user: User) -> Payment:
    order = db.scalar(select(Order).where(Order.id == order.id).with_for_update())
    if order.user_id != user.id:
        raise HTTPException(404, "Заказ не найден")
    if order.status != "pending":
        raise HTTPException(409, "Заказ уже обработан")
    existing = db.scalar(
        select(Payment)
        .where(Payment.order_id == order.id, Payment.provider == "yookassa")
        .order_by(Payment.created_at.desc())
    )
    if existing and existing.status in {"pending", "succeeded"}:
        return existing
    shop, secret, receipt = billing_config(db)
    data = YookassaClient(shop, secret).create(order, user, receipt=receipt)
    external_id = data.get("id")
    confirmation = (data.get("confirmation") or {}).get("confirmation_url")
    from urllib.parse import urlsplit

    url = urlsplit(confirmation or "")
    if (
        not isinstance(external_id, str)
        or not external_id
        or url.scheme != "https"
        or not url.hostname
        or url.username
        or url.password
    ):
        raise BillingError("ЮKassa не вернула идентификатор платежа")
    payment = Payment(
        order_id=order.id,
        user_id=user.id,
        provider="yookassa",
        external_id=external_id,
        status="pending",
        amount_minor=order.amount_minor,
        currency=order.currency,
        confirmation_url=confirmation,
        payload={"status": data.get("status"), "description": data.get("description")},
    )
    db.add(payment)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(Payment).where(
                Payment.provider == "yookassa", Payment.external_id == external_id
            )
        )
        if existing:
            return existing
        raise BillingError("Не удалось сохранить платёж") from None
    return payment


def _provider_amount(data: dict) -> tuple[int, str]:
    amount = data.get("amount") or {}
    try:
        return int(Decimal(str(amount["value"])) * 100), str(amount["currency"])
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        raise BillingError("ЮKassa вернула некорректную сумму") from exc


def confirm_yookassa_payment(db: Session, external_id: str, event_payload: dict) -> Payment:
    shop, secret, _ = billing_config(db)
    provider_data = YookassaClient(shop, secret).get(external_id)
    payment = db.scalar(
        select(Payment).where(Payment.provider == "yookassa", Payment.external_id == external_id)
    )
    if not payment:
        raise BillingError("Платёж не найден")
    order = db.scalar(select(Order).where(Order.id == payment.order_id).with_for_update())
    if provider_data.get("id") != payment.external_id or (provider_data.get("metadata") or {}).get(
        "order_id"
    ) != str(order.id):
        raise BillingError("Платёж не соответствует заказу")
    amount, currency = _provider_amount(provider_data)
    if amount != payment.amount_minor or currency != payment.currency:
        raise BillingError("Сумма платежа не совпадает с заказом")
    status = str(provider_data.get("status", ""))
    event_id = external_id + ":" + status
    seen = db.scalar(
        select(PaymentEvent).where(
            PaymentEvent.provider == "yookassa", PaymentEvent.event_id == event_id
        )
    )
    if not seen:
        db.add(
            PaymentEvent(
                provider="yookassa",
                event_id=event_id,
                payment_id=payment.id,
                payload={"status": status, "event": event_payload.get("event")},
            )
        )
    if status == "succeeded" and provider_data.get("paid") is True and payment.status == "pending":
        payment.status = "succeeded"
        payment.paid_at = utcnow()
        if order.status == "pending":
            order.status = "paid"
    elif status == "canceled" and payment.status == "pending":
        payment.status = "canceled"
    payment.payload = {"status": status, "event": event_payload.get("type")}
    db.commit()
    if payment.status == "succeeded" and order.status == "paid":
        try:
            provision_order(db, order.id, order.user_id)
        except HTTPException:
            db.rollback()
            # Payment is durable and can be retried by the admin after a panel outage.
    return payment


def confirm_stars_payment(
    db: Session,
    order: Order,
    telegram_payment_id: str,
    amount: int,
    currency: str,
    payload: dict,
) -> Payment:
    order = db.scalar(select(Order).where(Order.id == order.id).with_for_update())
    if order.status != "pending":
        existing = db.scalar(
            select(Payment).where(
                Payment.provider == "telegram_stars", Payment.external_id == telegram_payment_id
            )
        )
        if existing and existing.order_id == order.id:
            return existing
        raise BillingError("Заказ уже обработан")
    if currency != "XTR" or not order.stars_price or amount != order.stars_price:
        raise BillingError("Сумма Telegram Stars не совпадает с тарифом")
    existing = db.scalar(
        select(Payment).where(
            Payment.provider == "telegram_stars", Payment.external_id == telegram_payment_id
        )
    )
    if existing and existing.order_id != order.id:
        raise BillingError("Платёж уже привязан к другому заказу")
    if existing:
        return existing
    payment = Payment(
        order_id=order.id,
        user_id=order.user_id,
        provider="telegram_stars",
        external_id=telegram_payment_id,
        status="succeeded",
        amount_minor=amount,
        currency=currency,
        paid_at=utcnow(),
        payload=payload,
    )
    db.add(payment)
    db.flush()
    order.status = "paid"
    db.add(
        PaymentEvent(
            provider="telegram_stars",
            event_id=telegram_payment_id,
            payment_id=payment.id,
            payload=payload,
        )
    )
    db.commit()
    try:
        provision_order(db, order.id, order.user_id)
    except HTTPException:
        db.rollback()
    return payment
