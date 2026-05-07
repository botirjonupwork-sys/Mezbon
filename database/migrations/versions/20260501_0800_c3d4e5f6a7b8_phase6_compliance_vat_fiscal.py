"""phase6 compliance: VAT, fiscal QR, terms_accepted_at

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-01 08:00:00.000000

Roadmap Faza 6: QQS to'lovchi flag, fiskal QR kod, ToS qabul qilish vaqti.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('restaurants', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_vat_payer', sa.Boolean(), nullable=False, server_default=sa.text('0')))
        batch_op.add_column(sa.Column('vat_percent', sa.Float(), nullable=False, server_default='12.0'))

    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('fiscal_qr', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('fiscal_receipt_id', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('vat_amount_tiyin', sa.Integer(), nullable=True, server_default='0'))
        batch_op.add_column(sa.Column('terms_accepted_at', sa.DateTime(), nullable=True))
        batch_op.create_index('ix_orders_fiscal_receipt_id', ['fiscal_receipt_id'])


def downgrade() -> None:
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.drop_index('ix_orders_fiscal_receipt_id')
        batch_op.drop_column('terms_accepted_at')
        batch_op.drop_column('vat_amount_tiyin')
        batch_op.drop_column('fiscal_receipt_id')
        batch_op.drop_column('fiscal_qr')

    with op.batch_alter_table('restaurants', schema=None) as batch_op:
        batch_op.drop_column('vat_percent')
        batch_op.drop_column('is_vat_payer')
