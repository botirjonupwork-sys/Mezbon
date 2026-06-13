"""phase19 catering onsite limit

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-06-13 10:00:00.000000

Catering "borib yopib berish" (onsite) sig'imi: xizmat vaqti bo'yicha 2 soatlik
oynada restoran bo'yicha max N buyurtma. Admin sozlamadan o'zgartiradi.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3b4c5d6e7f8'
down_revision: Union[str, None] = 'f2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('restaurants', schema=None) as batch_op:
        batch_op.add_column(sa.Column('catering_onsite_max', sa.Integer(), nullable=False, server_default='8'))
        batch_op.add_column(sa.Column('catering_onsite_window_hours', sa.Float(), nullable=False, server_default='2'))


def downgrade() -> None:
    with op.batch_alter_table('restaurants', schema=None) as batch_op:
        batch_op.drop_column('catering_onsite_window_hours')
        batch_op.drop_column('catering_onsite_max')
