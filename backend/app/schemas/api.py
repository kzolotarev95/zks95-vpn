from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.security import as_utc


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_validator("*", mode="after")
    @classmethod
    def normalize_datetime(cls, value):
        return as_utc(value) if isinstance(value, datetime) else value


class UserOut(ORMModel):
    id: UUID
    email: str
    created_at: datetime


class PlanOut(ORMModel):
    id: UUID
    code: str
    name: str
    description: str
    price_minor: int
    currency: str
    duration_days: int
    device_limit: int


class CreateOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_id: UUID


class OrderOut(ORMModel):
    id: UUID
    plan_id: UUID
    plan_name: str
    amount_minor: int
    currency: str
    duration_days: int
    device_limit: int
    status: str
    created_at: datetime


class SubscriptionOut(ORMModel):
    id: UUID
    plan_name: str
    device_limit: int
    status: str
    starts_at: datetime
    expires_at: datetime
