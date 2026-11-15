import json
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.encryption import decrypt, encrypt
from app.core.security import utcnow
from app.integrations.vpn import Panel, PanelError
from app.models.entities import AuditLog, Subscription, VpnProvider
from app.services.admin import AdminContext, permission
from app.services.vpn import panel, provision_order, refresh_access

router = APIRouter(prefix="/api/v1/admin", tags=["VPN panels"])


class ProviderWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["3x-ui", "remnawave"]
    base_url: str = Field(max_length=1024)
    token: SecretStr | None = None
    username: str | None = Field(default=None, max_length=128)
    password: SecretStr | None = None
    api_mode: Literal["modern", "legacy"] = "modern"
    inbound_ids: list[int] = Field(default_factory=list, max_length=32)
    squad_ids: list[UUID] = Field(default_factory=list, max_length=32)
    subscription_base_url: str = Field(default="", max_length=1024)
    traffic_limit_bytes: int = Field(default=0, ge=0, le=2**53 - 1)
    flow: Literal["", "xtls-rprx-vision"] = ""
    is_active: bool = True

    @field_validator("base_url", "subscription_base_url")
    @classmethod
    def url(cls, value):
        if not value:
            return value
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Нужен http(s) URL без логина, query и fragment")
        return value.rstrip("/")

    @model_validator(mode="after")
    def correct_options(self):
        if not self.base_url:
            raise ValueError("Укажите URL панели")
        if self.kind == "3x-ui":
            if not self.inbound_ids or any(i <= 0 for i in self.inbound_ids):
                raise ValueError("Укажите положительные inbound IDs")
            if not self.subscription_base_url:
                raise ValueError("Укажите публичный URL подписок 3x-ui, включая /sub")
            if self.api_mode == "legacy" and len(self.inbound_ids) != 1:
                raise ValueError("Legacy 3x-ui поддерживает один VLESS/VMess inbound")
        elif not self.squad_ids:
            raise ValueError("Укажите хотя бы один internal squad UUID")
        return self


def view(row: VpnProvider):
    return {
        "id": row.id,
        "name": row.name,
        "kind": row.kind,
        "base_url": row.base_url,
        "is_active": row.is_active,
        "checked_at": row.checked_at,
        "configured": bool(row.credentials_encrypted),
        **row.options,
    }


@router.get("/providers")
def providers(
    admin: AdminContext = Depends(permission("providers")),
    db: Session = Depends(get_db),
):
    return [view(row) for row in db.scalars(select(VpnProvider).order_by(VpnProvider.name))]


def save(body: ProviderWrite, db: Session, admin: AdminContext, provider_id=None):
    row = db.get(VpnProvider, provider_id) if provider_id else None
    if provider_id and not row:
        raise HTTPException(404, "Панель не найдена")
    if row and (row.kind != body.kind or row.base_url != body.base_url):
        raise HTTPException(409, "Для другого сервера создайте отдельное подключение")
    credentials = json.loads(decrypt(row.credentials_encrypted)) if row else {}
    if body.token and body.token.get_secret_value():
        credentials = {"token": body.token.get_secret_value()}
    elif body.password and body.password.get_secret_value() and body.username:
        credentials = {"username": body.username, "password": body.password.get_secret_value()}
    if not credentials:
        raise HTTPException(422, "Укажите API-токен или логин и пароль 3x-ui")
    if body.kind == "remnawave" and not credentials.get("token"):
        raise HTTPException(422, "Для Remnawave нужен API-токен")
    options = body.model_dump(
        mode="json",
        exclude={
            "name",
            "kind",
            "base_url",
            "token",
            "username",
            "password",
            "is_active",
        },
    )
    try:
        with Panel(body.kind, body.base_url, credentials, options) as adapter:
            adapter.check()
    except PanelError as exc:
        raise HTTPException(502, str(exc)) from None
    if not row:
        row = VpnProvider()
        db.add(row)
    row.name, row.kind, row.base_url = body.name, body.kind, body.base_url
    row.credentials_encrypted, row.options = encrypt(json.dumps(credentials)), options
    row.is_active, row.checked_at = body.is_active, utcnow()
    db.flush()
    db.add(AuditLog(actor_id=admin.user.id, action="vpn.provider_save", target_id=str(row.id)))
    db.commit()
    return view(row)


@router.post("/providers", status_code=201)
def create(
    body: ProviderWrite,
    admin: AdminContext = Depends(permission("providers:write")),
    db: Session = Depends(get_db),
):
    return save(body, db, admin)


@router.put("/providers/{provider_id}")
def update(
    provider_id: UUID,
    body: ProviderWrite,
    admin: AdminContext = Depends(permission("providers:write")),
    db: Session = Depends(get_db),
):
    return save(body, db, admin, provider_id)


@router.post("/providers/{provider_id}/check")
def check(
    provider_id: UUID,
    admin: AdminContext = Depends(permission("providers:write")),
    db: Session = Depends(get_db),
):
    row = db.get(VpnProvider, provider_id)
    if not row:
        raise HTTPException(404, "Панель не найдена")
    try:
        with panel(row) as adapter:
            adapter.check()
    except PanelError as exc:
        raise HTTPException(502, str(exc)) from None
    row.checked_at = utcnow()
    db.commit()
    return view(row)


@router.post("/orders/{order_id}/grant")
def manual_grant(
    order_id: UUID,
    admin: AdminContext = Depends(permission("subscriptions:write")),
    db: Session = Depends(get_db),
):
    # This is an explicit owner grant, never a simulated payment confirmation.
    return provision_order(db, order_id, admin.user.id, manual=True)


@router.post("/subscriptions/{subscription_id}/refresh")
def refresh(
    subscription_id: UUID,
    admin: AdminContext = Depends(permission("subscriptions:write")),
    db: Session = Depends(get_db),
):
    sub = db.get(Subscription, subscription_id)
    if not sub:
        raise HTTPException(404, "Подписка не найдена")
    return refresh_access(db, sub)
