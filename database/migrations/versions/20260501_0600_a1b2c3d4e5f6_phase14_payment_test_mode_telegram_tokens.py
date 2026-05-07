"""phase1.4 payment test_mode + telegram provider tokens

Revision ID: a1b2c3d4e5f6
Revises: c73f875397ff
Create Date: 2026-05-01 06:00:00.000000

Roadmap Faza 1.4: per-restaurant Telegram payment tokens + test/live toggle.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'c73f875397ff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('restaurants', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'payment_test_mode', sa.Boolean(), nullable=False, server_default=sa.text('1')
        ))
        batch_op.add_column(sa.Column('telegram_provider_token_click', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('telegram_provider_token_payme', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('restaurants', schema=None) as batch_op:
        batch_op.drop_column('telegram_provider_token_payme')
        batch_op.drop_column('telegram_provider_token_click')
        batch_op.drop_column('payment_test_mode')
