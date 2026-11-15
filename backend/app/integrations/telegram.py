import re

import httpx
from fastapi import HTTPException


def validate_bot_token(token: str) -> dict:
    # Never log an HTTP exception: Telegram embeds the credential in the URL.
    if not re.fullmatch(r"[0-9]{5,20}:[A-Za-z0-9_-]{20,200}", token):
        raise HTTPException(422, "Некорректный токен BotFather")
    try:
        with httpx.Client(timeout=10, follow_redirects=False) as client:
            profile = client.get(f"https://api.telegram.org/bot{token}/getMe")
            if profile.status_code in {401, 404}:
                raise HTTPException(422, "Telegram отклонил токен")
            profile.raise_for_status()
            result = profile.json()
            webhook = client.get(f"https://api.telegram.org/bot{token}/getWebhookInfo")
            webhook.raise_for_status()
            if webhook.json().get("result", {}).get("url"):
                raise HTTPException(
                    409, "Бот использует webhook. Сначала отключите его у прежнего сервиса"
                )
            if not result.get("ok") or not result.get("result", {}).get("is_bot"):
                raise HTTPException(422, "Не удалось проверить бота")
            return result["result"]
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "Telegram временно недоступен") from None
