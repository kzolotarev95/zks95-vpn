import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import HTTPException


def verify_init_data(init_data: str, bot_token: str, max_age: int = 86_400) -> dict:
    if not init_data or not bot_token:
        raise HTTPException(401, "Telegram Mini App не авторизован")
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received = pairs.pop("hash", "")
    if not received:
        raise HTTPException(401, "Некорректные данные Telegram")
    check = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise HTTPException(401, "Подпись Telegram недействительна")
    try:
        auth_date = int(pairs.get("auth_date", "0"))
        now = time.time()
        if now - auth_date > max_age or auth_date - now > 60:
            raise HTTPException(401, "Сессия Telegram устарела")
        user = json.loads(pairs["user"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(401, "Telegram не передал пользователя") from exc
    if not isinstance(user, dict) or not user.get("id"):
        raise HTTPException(401, "Telegram не передал пользователя")
    return user
