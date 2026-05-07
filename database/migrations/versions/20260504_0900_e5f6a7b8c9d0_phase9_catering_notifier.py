"""phase9 catering notifier chat_id

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-04 09:00:00.000000

Restaurant'ga `catering_notifier_chat_id` — ertangi catering ro'yxati
yuboriladigan Telegram kanal/guruh chat ID.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('restaurants', schema=None) as batch_op:
        batch_op.add_column(sa.Column('catering_notifier_chat_id', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('restaurants', schema=None) as batch_op:
        batch_op.drop_column('catering_notifier_chat_id')
