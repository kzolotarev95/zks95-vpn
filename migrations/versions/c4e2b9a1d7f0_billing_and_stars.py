"""billing_and_stars

Revision ID: c4e2b9a1d7f0
Revises: b8dc08138968
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4e2b9a1d7f0"
down_revision: str | None = "b8dc08138968"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("plans") as batch:
        batch.add_column(sa.Column("stars_price", sa.Integer(), nullable=True))
    with op.batch_alter_table("orders") as batch:
        batch.add_column(sa.Column("stars_price", sa.Integer(), nullable=True))

    op.create_table(
        "billing_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("yookassa_shop_id", sa.String(length=64), nullable=True),
        sa.Column("yookassa_secret_encrypted", sa.Text(), nullable=True),
        sa.Column("yookassa_receipt_enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_billing_settings_singleton")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_billing_settings")),
    )
    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("confirmation_url", sa.String(length=2048), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'succeeded', 'canceled', 'refunded')",
            name=op.f("ck_payments_status"),
        ),
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.id"], name=op.f("fk_payments_order_id_orders")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_payments_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
        sa.UniqueConstraint("provider", "external_id", name=op.f("uq_payments_provider")),
    )
    op.create_index(op.f("ix_payments_order_id"), "payments", ["order_id"])
    op.create_index(op.f("ix_payments_user_id"), "payments", ["user_id"])
    op.create_table(
        "payment_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["payment_id"], ["payments.id"], name=op.f("fk_payment_events_payment_id_payments")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_events")),
        sa.UniqueConstraint("provider", "event_id", name=op.f("uq_payment_events_provider")),
    )


def downgrade() -> None:
    op.drop_table("payment_events")
    op.drop_index(op.f("ix_payments_user_id"), table_name="payments")
    op.drop_index(op.f("ix_payments_order_id"), table_name="payments")
    op.drop_table("payments")
    op.drop_table("billing_settings")
    with op.batch_alter_table("orders") as batch:
        batch.drop_column("stars_price")
    with op.batch_alter_table("plans") as batch:
        batch.drop_column("stars_price")
