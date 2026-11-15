import argparse

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.entities import Plan, Role


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


def main() -> None:
    parser = argparse.ArgumentParser(description="ZKS95 VPN maintenance")
    parser.add_argument("command", choices=["seed"])
    parser.parse_args()
    seed()


if __name__ == "__main__":
    main()
