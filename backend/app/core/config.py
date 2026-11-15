from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+psycopg://zks95:local-only@postgres:5432/zks95"
    redis_url: str = "redis://redis:6379/0"
    public_url: str = "http://localhost:8080"
    cookie_secure: bool = False
    session_hours: int = Field(default=168, ge=1, le=720)
    trusted_hosts: list[str] = ["localhost", "127.0.0.1", "testserver", "api"]
    enable_docs: bool = True
    rate_limit_enabled: bool = True
    app_encryption_key: str = ""
    bot_service_token: str = ""
    api_internal_url: str = "http://api:8000"
    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""
    yookassa_receipt_enabled: bool = False
    yookassa_vat_code: int = Field(default=1, ge=1, le=6)
    miniapp_url: str = ""

    @model_validator(mode="after")
    def production_settings(self) -> "Settings":
        if self.environment == "production":
            if not self.cookie_secure or not self.public_url.startswith("https://"):
                raise ValueError("Production requires HTTPS and COOKIE_SECURE=true")
            if "local-only" in self.database_url:
                raise ValueError("Configure a unique database password for production")
            if "*" in self.trusted_hosts:
                raise ValueError("Production requires explicit TRUSTED_HOSTS")
            if not self.rate_limit_enabled:
                raise ValueError("Production requires rate limiting")
            if not self.app_encryption_key:
                raise ValueError("Production requires APP_ENCRYPTION_KEY")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
