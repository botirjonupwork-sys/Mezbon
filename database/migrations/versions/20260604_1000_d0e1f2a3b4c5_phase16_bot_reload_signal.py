"""phase16 bot menejeri restart signali — restaurants.bot_reload_at

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-06-04 10:00:00.000000

Bot menejeri (bot/manager.py) bu ustunni poll qiladi: API restart so'rovida
now() qo'yiladi → menejer shu restoran botini qayta ishga tushiradi.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd0e1f2a3b4c5'
down_revision: Union[str, None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('restaurants', schema=None) as batch_op:
        batch_op.add_column(sa.Column('bot_reload_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('restaurants', schema=None) as batch_op:
        batch_op.drop_column('bot_reload_at')
