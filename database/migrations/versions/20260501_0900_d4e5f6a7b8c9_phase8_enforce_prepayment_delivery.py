"""phase8 enforce prepayment for delivery types

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-01 09:00:00.000000

Restaurant'ga `enforce_prepayment_for_delivery` flag — yoqilgan bo'lsa,
har bir delivery/onsite_catering buyurtma summa chegarasidan qat'i nazar
oldindan to'lov talab qiladi. Pickup esa hech qachon prepayment talab qilmaydi.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('restaurants', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'enforce_prepayment_for_delivery', sa.Boolean(),
            nullable=False, server_default=sa.text('0')
        ))


def downgrade() -> None:
    with op.batch_alter_table('restaurants', schema=None) as batch_op:
        batch_op.drop_column('enforce_prepayment_for_delivery')
