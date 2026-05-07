"""phase3 refund model

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-01 07:00:00.000000

Roadmap Faza 3.1: Refund model — to'lov qaytarish yozuvi.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'refunds',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('payment_id', sa.Integer(), sa.ForeignKey('payments.id'), nullable=True),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('orders.id'), nullable=True),
        sa.Column('restaurant_id', sa.Integer(), sa.ForeignKey('restaurants.id'), nullable=False),
        sa.Column('amount_tiyin', sa.Integer(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('provider', sa.String(), nullable=True),
        sa.Column('provider_refund_id', sa.String(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('requested_by_admin_id', sa.Integer(), sa.ForeignKey('admins.id'), nullable=True),
        sa.Column('requested_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_refunds_payment_id', 'refunds', ['payment_id'])
    op.create_index('ix_refunds_order_id', 'refunds', ['order_id'])
    op.create_index('ix_refunds_restaurant_id', 'refunds', ['restaurant_id'])
    op.create_index('ix_refunds_provider_refund_id', 'refunds', ['provider_refund_id'])


def downgrade() -> None:
    op.drop_index('ix_refunds_provider_refund_id', table_name='refunds')
    op.drop_index('ix_refunds_restaurant_id', table_name='refunds')
    op.drop_index('ix_refunds_order_id', table_name='refunds')
    op.drop_index('ix_refunds_payment_id', table_name='refunds')
    op.drop_table('refunds')
