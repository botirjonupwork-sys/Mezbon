"""phase11 direct payment app links (Click/Payme/Uzum)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-05-22 20:00:00.000000

Restoran modeli:
  + uzum_service_id, uzum_webhook_user, uzum_webhook_pass, uzum_enabled

Order modeli (direct app link payment tracking):
  + merchant_trans_id (unique idempotency kalit)
  + payment_url        — generatsiya qilingan deep link
  + payment_error      — xato sabab
  + payment_paid_at    — webhook tasdig'i vaqti
  + provider_tx_id     — provayder tomondagi tranzaksiya ID
  + click_prepare_id   — Click prepare bosqichidagi ID

Hozirgi yandex_*, payment_charge_id, va Telegram Payments maydonlari saqlanadi
(tarixiy buyurtmalar uchun).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Restaurant — Uzum maydonlari
    with op.batch_alter_table('restaurants', schema=None) as batch_op:
        batch_op.add_column(sa.Column('uzum_service_id', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('uzum_webhook_user', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('uzum_webhook_pass', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('uzum_enabled', sa.Boolean(), nullable=True, server_default=sa.false()))

    # Order — direct payment maydonlari
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('merchant_trans_id', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('payment_url', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('payment_error', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('payment_paid_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('provider_tx_id', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('click_prepare_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_orders_merchant_trans_id', ['merchant_trans_id'], unique=True)
        batch_op.create_index('ix_orders_provider_tx_id', ['provider_tx_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.drop_index('ix_orders_provider_tx_id')
        batch_op.drop_index('ix_orders_merchant_trans_id')
        batch_op.drop_column('click_prepare_id')
        batch_op.drop_column('provider_tx_id')
        batch_op.drop_column('payment_paid_at')
        batch_op.drop_column('payment_error')
        batch_op.drop_column('payment_url')
        batch_op.drop_column('merchant_trans_id')

    with op.batch_alter_table('restaurants', schema=None) as batch_op:
        batch_op.drop_column('uzum_enabled')
        batch_op.drop_column('uzum_webhook_pass')
        batch_op.drop_column('uzum_webhook_user')
        batch_op.drop_column('uzum_service_id')
