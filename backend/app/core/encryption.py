from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

from app.core.config import get_settings


def cipher() -> Fernet:
    try:
        return Fernet(get_settings().app_encryption_key.encode())
    except (ValueError, TypeError) as exc:
        raise HTTPException(503, "Ключ шифрования не настроен на сервере") from exc


def encrypt(value: str) -> str:
    return cipher().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    try:
        return cipher().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise HTTPException(503, "Не удалось расшифровать настройки сервиса") from exc
