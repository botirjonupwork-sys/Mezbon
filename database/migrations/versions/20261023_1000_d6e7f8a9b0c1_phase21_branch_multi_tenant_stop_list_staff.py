"""phase21 branch multi-tenant stop-list and staff

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-10-23 10:00:00.000000

Multi-Tenant Filial kengaytmasi:
- branches: landmark, is_delivery_enabled, is_takeaway_enabled, kitchen_chat_id, cashier_chat_id, max_delivery_radius_km
- branch_products: filial stop-list va narx override
- staff_members: filial xodimlari (kassir, oshxona, filial menejeri)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d6e7f8a9b0c1"
down_revision: Union[str, None] = "c5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = insp.get_table_names()

    # 1. branches jadvaliga yangi ustunlar qo'shish (mavjud bo'lmasa)
    branch_cols = [c["name"] for c in insp.get_columns("branches")]
    with op.batch_alter_table("branches", schema=None) as batch_op:
        if "landmark" not in branch_cols:
            batch_op.add_column(sa.Column("landmark", sa.String(255), nullable=True))
        if "is_delivery_enabled" not in branch_cols:
            batch_op.add_column(sa.Column("is_delivery_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
        if "is_takeaway_enabled" not in branch_cols:
            batch_op.add_column(sa.Column("is_takeaway_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
        if "kitchen_chat_id" not in branch_cols:
            batch_op.add_column(sa.Column("kitchen_chat_id", sa.String(64), nullable=True))
        if "cashier_chat_id" not in branch_cols:
            batch_op.add_column(sa.Column("cashier_chat_id", sa.String(64), nullable=True))
        if "max_delivery_radius_km" not in branch_cols:
            batch_op.add_column(sa.Column("max_delivery_radius_km", sa.Float(), nullable=False, server_default="15.0"))

    # 2. branch_products jadvalini yaratish (mavjud bo'lmasa)
    if "branch_products" not in existing_tables:
        op.create_table(
            "branch_products",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
            sa.Column("is_available", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("override_price", sa.Float(), nullable=True),
            sa.Column("preparation_time_min", sa.Integer(), nullable=False, server_default="15"),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
            sa.UniqueConstraint("branch_id", "product_id", name="uq_branch_product"),
        )
        op.create_index(
            "idx_branch_product_available",
            "branch_products",
            ["branch_id", "product_id", "is_available"],
            unique=False,
        )

    # 3. staff_members jadvalini yaratish (mavjud bo'lmasa)
    if "staff_members" not in existing_tables:
        op.create_table(
            "staff_members",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=True),
            sa.Column("username", sa.String(64), nullable=False),
            sa.Column("password_hash", sa.String(255), nullable=False),
            sa.Column("full_name", sa.String(128), nullable=False),
            sa.Column("phone", sa.String(32), nullable=True),
            sa.Column("role", sa.String(32), nullable=False, server_default="cashier"),
            sa.Column("telegram_chat_id", sa.String(64), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
            sa.UniqueConstraint("username", name="uq_staff_username"),
        )
        op.create_index(
            "idx_staff_branch_role",
            "staff_members",
            ["branch_id", "role"],
            unique=False,
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = insp.get_table_names()

    if "staff_members" in existing_tables:
        op.drop_index("idx_staff_branch_role", table_name="staff_members")
        op.drop_table("staff_members")

    if "branch_products" in existing_tables:
        op.drop_index("idx_branch_product_available", table_name="branch_products")
        op.drop_table("branch_products")

    with op.batch_alter_table("branches", schema=None) as batch_op:
        batch_op.drop_column("max_delivery_radius_km")
        batch_op.drop_column("cashier_chat_id")
        batch_op.drop_column("kitchen_chat_id")
        batch_op.drop_column("is_takeaway_enabled")
        batch_op.drop_column("is_delivery_enabled")
        batch_op.drop_column("landmark")

