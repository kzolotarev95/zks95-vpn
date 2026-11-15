from datetime import datetime
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, SecretStr

from app.schemas.api import ORMModel, UserOut


class AdminCredentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    login: str = Field(
        min_length=1, max_length=254, validation_alias=AliasChoices("login", "email")
    )
    password: str = Field(min_length=5, max_length=128)
    otp: str | None = Field(default=None, pattern=r"^[0-9]{6}$")


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=5, max_length=128)


class AdminProfile(UserOut):
    role: str
    permissions: list[str]


class PlanWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=2, max_length=32, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=2000)
    price_minor: int = Field(gt=0, le=100_000_000)
    duration_days: int = Field(gt=0, le=3650)
    device_limit: int = Field(gt=0, le=100)
    is_active: bool = True
    provider_id: UUID | None = None


class UserState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_active: bool


class AdminUserOut(UserOut):
    is_active: bool
    telegram_id: int | None = None
    telegram_username: str | None = None
    display_name: str | None = None
    role: str | None = None


class AuditOut(ORMModel):
    id: UUID
    actor_id: UUID | None
    action: str
    target_id: str | None
    created_at: datetime


class TelegramWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: SecretStr | None = None
    enabled: bool
    support_username: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_]{5,32}$")


class TelegramStatus(BaseModel):
    configured: bool = False
    enabled: bool = False
    username: str | None = None
    bot_id: int | None = None
    support_username: str | None = None
    connected: bool = False
    last_seen_at: datetime | None = None
    last_error: str | None = None
