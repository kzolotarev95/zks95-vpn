from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import as_utc, token_digest, utcnow
from app.models.entities import User, UserSession

COOKIE_NAME = "zks95_session"


def get_current_session(request: Request, db: Session = Depends(get_db)) -> UserSession:
    token = request.cookies.get(COOKIE_NAME)
    if not token or len(token) > 256:
        raise HTTPException(401, "Необходим вход в аккаунт")
    session = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == token_digest(token), UserSession.purpose == "user"
        )
    )
    if session is None or as_utc(session.expires_at) <= utcnow():
        raise HTTPException(401, "Сессия истекла")
    return session


def get_current_user(
    session: UserSession = Depends(get_current_session), db: Session = Depends(get_db)
) -> User:
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(401, "Аккаунт недоступен")
    return user
