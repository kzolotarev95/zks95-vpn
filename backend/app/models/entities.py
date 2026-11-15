import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.security import utcnow


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str | None] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    purpose: Mapped[str] = mapped_column(String(16), default="user", server_default="user")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True)


class AdminUser(Base):
    __tablename__ = "admin_users"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    totp_secret_encrypted: Mapped[str | None] = mapped_column(Text)
    last_totp_step: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")


class Plan(Base):
    __tablename__ = "plans"
    __table_args__ = (
        CheckConstraint("price_minor > 0", name="positive_price"),
        CheckConstraint("duration_days > 0", name="positive_duration"),
        CheckConstraint("device_limit > 0", name="positive_device_limit"),
        CheckConstraint("currency = 'RUB'", name="supported_currency"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    price_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    duration_days: Mapped[int] = mapped_column(Integer)
    device_limit: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    provider_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vpn_providers.id"))


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key"),
        CheckConstraint("amount_minor > 0", name="positive_amount"),
        CheckConstraint("duration_days > 0", name="positive_duration"),
        CheckConstraint("device_limit > 0", name="positive_device_limit"),
        CheckConstraint("currency = 'RUB'", name="supported_currency"),
        CheckConstraint("status IN ('pending', 'paid', 'cancelled', 'refunded')", name="status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plans.id"))
    idempotency_key: Mapped[str] = mapped_column(String(64))
    amount_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    plan_name: Mapped[str] = mapped_column(String(100))
    duration_days: Mapped[int] = mapped_column(Integer)
    device_limit: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    provider_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vpn_providers.id"))


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint("expires_at > starts_at", name="valid_period"),
        CheckConstraint("device_limit > 0", name="positive_device_limit"),
        CheckConstraint("status IN ('active', 'expired', 'revoked')", name="status"),
        Index("ix_subscriptions_user_status", "user_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), unique=True)
    plan_name: Mapped[str] = mapped_column(String(100))
    device_limit: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="active")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    target_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TelegramAccount(Base):
    __tablename__ = "telegram_accounts"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    username: Mapped[str | None] = mapped_column(String(64))
    display_name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TelegramSettings(Base):
    __tablename__ = "telegram_settings"
    __table_args__ = (CheckConstraint("id = 1", name="singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_encrypted: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    bot_id: Mapped[int | None] = mapped_column(BigInteger)
    username: Mapped[str | None] = mapped_column(String(64))
    support_username: Mapped[str | None] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(Integer, default=0)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(64))


class TelegramLink(Base):
    __tablename__ = "telegram_links"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class VpnProvider(Base):
    __tablename__ = "vpn_providers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(24))
    base_url: Mapped[str] = mapped_column(String(1024))
    credentials_encrypted: Mapped[str] = mapped_column(Text)
    options: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VpnAccess(Base):
    __tablename__ = "vpn_access"

    subscription_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subscriptions.id"), primary_key=True
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vpn_providers.id"))
    remote_username: Mapped[str] = mapped_column(String(64), unique=True)
    identity_encrypted: Mapped[str] = mapped_column(Text)
    connection_encrypted: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    used_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
