import secrets
import time
from dataclasses import dataclass

import pyotp
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.encryption import decrypt
from app.core.security import as_utc, token_digest, utcnow
from app.models.entities import AdminUser, Role, User, UserSession

ADMIN_COOKIE = "zks95_admin"
PERMISSIONS = {
    "SuperAdmin": {
        "overview",
        "users",
        "users:write",
        "plans",
        "plans:write",
        "orders",
        "subscriptions",
        "subscriptions:write",
        "audit",
        "telegram",
        "providers",
        "providers:write",
    },
    "Admin": {
        "overview",
        "users",
        "users:write",
        "plans",
        "plans:write",
        "orders",
        "subscriptions",
        "subscriptions:write",
        "audit",
        "providers",
    },
    "Support": {"overview", "users", "orders", "subscriptions"},
    "Finance": {"overview", "plans", "orders", "subscriptions"},
}


@dataclass
class AdminContext:
    user: User
    membership: AdminUser
    session: UserSession
    role: str

    def require(self, permission: str) -> None:
        if permission not in PERMISSIONS.get(self.role, set()):
            raise HTTPException(403, "Недостаточно прав")


def get_admin(request: Request, db: Session = Depends(get_db)) -> AdminContext:
    token = request.cookies.get(ADMIN_COOKIE, "")
    if not token or len(token) > 256:
        raise HTTPException(401, "Войдите в административную панель")
    session = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == token_digest(token), UserSession.purpose == "admin"
        )
    )
    if not session or as_utc(session.expires_at) <= utcnow():
        raise HTTPException(401, "Сессия администратора истекла")
    user = db.get(User, session.user_id)
    member = db.get(AdminUser, session.user_id)
    if not user or not user.is_active or not member:
        raise HTTPException(403, "Административный доступ недоступен")
    role = db.get(Role, member.role_id)
    if not role or role.name not in PERMISSIONS:
        raise HTTPException(403, "Роль не настроена")
    return AdminContext(user, member, session, role.name)


def permission(name: str):
    def check(admin: AdminContext = Depends(get_admin)) -> AdminContext:
        admin.require(name)
        return admin

    return check


def verify_totp(member: AdminUser, code: str, db: Session) -> bool:
    if not member.mfa_enabled or not member.totp_secret_encrypted:
        return False
    totp = pyotp.TOTP(decrypt(member.totp_secret_encrypted))
    now_step = int(time.time()) // 30
    for step in (now_step - 1, now_step, now_step + 1):
        if step > member.last_totp_step and secrets.compare_digest(totp.at(step * 30), code):
            # A conditional write protects against simultaneous replay even on SQLite.
            from sqlalchemy import update

            updated = db.execute(
                update(AdminUser)
                .where(AdminUser.user_id == member.user_id, AdminUser.last_totp_step < step)
                .values(last_totp_step=step)
            )
            return updated.rowcount == 1
    return False
