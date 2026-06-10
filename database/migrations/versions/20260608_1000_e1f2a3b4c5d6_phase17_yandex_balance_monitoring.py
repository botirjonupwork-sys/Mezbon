"""phase17 Yandex balance monitoring

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-06-08 10:00:00.000000

Yandex Delivery hisob balansi uchun restoran darajasida monitoring maydonlari.
Hozir source manual/mock; real balans endpoint tasdiqlansa service shu ustunlarni
avtomatik yangilaydi.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, None] = 'd0e1f2a3b4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('restaurants', schema=None) as batch_op:
        batch_op.add_column(sa.Column('yandex_balance_monitor_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('yandex_balance_amount', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('yandex_balance_currency', sa.String(), nullable=True, server_default='UZS'))
        batch_op.add_column(sa.Column('yandex_balance_checked_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('yandex_balance_low_threshold', sa.Float(), nullable=False, server_default='300000'))
        batch_op.add_column(sa.Column('yandex_balance_critical_threshold', sa.Float(), nullable=False, server_default='100000'))
        batch_op.add_column(sa.Column('yandex_balance_status', sa.String(), nullable=False, server_default='unknown'))
        batch_op.add_column(sa.Column('yandex_balance_last_alert_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('yandex_balance_source', sa.String(), nullable=False, server_default='manual'))
        batch_op.add_column(sa.Column('yandex_balance_block_on_critical', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table('restaurants', schema=None) as batch_op:
        batch_op.drop_column('yandex_balance_block_on_critical')
        batch_op.drop_column('yandex_balance_source')
        batch_op.drop_column('yandex_balance_last_alert_at')
        batch_op.drop_column('yandex_balance_status')
        batch_op.drop_column('yandex_balance_critical_threshold')
        batch_op.drop_column('yandex_balance_low_threshold')
        batch_op.drop_column('yandex_balance_checked_at')
        batch_op.drop_column('yandex_balance_currency')
        batch_op.drop_column('yandex_balance_amount')
        batch_op.drop_column('yandex_balance_monitor_enabled')
