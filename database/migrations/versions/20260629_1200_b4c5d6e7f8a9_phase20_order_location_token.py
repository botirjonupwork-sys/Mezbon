"""phase20 order location_token (SMS pin-havola)

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-06-29 12:00:00.000000

Telefon buyurtmalari uchun mijozdan aniq lat/lon olish: order'ga location_token
qo'shiladi — SMS pin-havola shu token orqali order'ni topadi.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b4c5d6e7f8a9'
down_revision: Union[str, None] = 'a3b4c5d6e7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('location_token', sa.String(), nullable=True))
        batch_op.create_index('ix_orders_location_token', ['location_token'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.drop_index('ix_orders_location_token')
        batch_op.drop_column('location_token')
