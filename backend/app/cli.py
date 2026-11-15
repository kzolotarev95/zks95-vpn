import argparse
import getpass
import sys

import pyotp
from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.encryption import encrypt
from app.core.security import hash_password, verify_password
from app.models.entities import AdminUser, AuditLog, Plan, Role, User, UserSession


def seed() -> None:
    with SessionLocal.begin() as db:
        for name in ("SuperAdmin", "Admin", "Support", "Finance"):
            if not db.scalar(select(Role).where(Role.name == name)):
                db.add(Role(name=name))
        for code, name, days, price, devices in (
            ("month", "Месяц", 30, 19900, 3),
            ("quarter", "Три месяца", 90, 49900, 5),
            ("year", "Год", 365, 169000, 5),
        ):
            if not db.scalar(select(Plan).where(Plan.code == code)):
                db.add(
                    Plan(
                        code=code,
                        name=name,
                        description="Личный защищённый доступ",
                        duration_days=days,
                        price_minor=price,
                        device_limit=devices,
                    )
                )
    print("Initial catalog and roles are ready. Existing records were preserved.")


def create_admin(email: str, role_name: str, reset_mfa: bool = False) -> None:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise SystemExit("Use an interactive terminal: docker compose exec api ... (without -T).")
    try:
        email = validate_email(email, check_deliverability=False).normalized.lower()
    except EmailNotValidError as exc:
        raise SystemExit(f"Invalid email: {exc}") from None
    secret = pyotp.random_base32()
    encrypted = encrypt(secret)
    with SessionLocal.begin() as db:
        role = db.scalar(select(Role).where(Role.name == role_name))
        if not role:
            raise SystemExit(f"Unknown role: {role_name}")
        user = db.scalar(select(User).where(User.email == email))
        member = db.get(AdminUser, user.id) if user else None
        if member and not reset_mfa:
            raise SystemExit("Admin already exists. Use --reset-mfa only to recover 2FA.")
        password = getpass.getpass("Existing account password: " if user else "New password: ")
        if user:
            if not user.password_hash or not verify_password(password, user.password_hash):
                raise SystemExit("Incorrect account password.")
            if not user.is_active:
                raise SystemExit("Account is disabled.")
        elif len(password) < 12 or password != getpass.getpass("Repeat password: "):
            raise SystemExit("Passwords must match and contain at least 12 characters.")
        print("Add a time-based code in your authenticator. Issuer: ZKS95 VPN; account:", email)
        print("Setup key (shown only in this interactive terminal):", secret)
        if not pyotp.TOTP(secret).verify(input("Current six-digit code: ").strip(), valid_window=1):
            raise SystemExit("Incorrect code. Nothing was saved; run the command again.")
        if not user:
            user = User(email=email, password_hash=hash_password(password))
            db.add(user)
            db.flush()
        if not member:
            member = AdminUser(user_id=user.id, role_id=role.id)
            db.add(member)
        member.role_id = role.id
        member.mfa_enabled = True
        member.totp_secret_encrypted = encrypted
        member.last_totp_step = 0
        from sqlalchemy import delete

        db.execute(
            delete(UserSession).where(
                UserSession.user_id == user.id, UserSession.purpose == "admin"
            )
        )
        db.add(
            AuditLog(
                actor_id=user.id,
                action="admin.reset_mfa" if reset_mfa else "admin.bootstrap",
                target_id=str(user.id),
            )
        )
    print(f"Admin created: {email} ({role_name})")
    print("Open /admin and sign in with your email, password and a current 2FA code.")


def main() -> None:
    parser = argparse.ArgumentParser(description="ZKS95 VPN maintenance")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("seed")
    admin_parser = subparsers.add_parser("admin-create")
    admin_parser.add_argument("--email", required=True)
    admin_parser.add_argument("--reset-mfa", action="store_true")
    admin_parser.add_argument(
        "--role", choices=["SuperAdmin", "Admin", "Support", "Finance"], default="SuperAdmin"
    )
    args = parser.parse_args()
    if args.command == "seed":
        seed()
    else:
        create_admin(args.email, args.role, args.reset_mfa)


if __name__ == "__main__":
    main()
