"""phase18 security AI alerts

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-06-11 10:00:00.000000

Xavfsizlik AI bildirishnoma tizimi uchun jadvallar:
- alert_channels — kanal sozlamalari (Telegram, kelajakda email/webhook/sms)
- alert_rules    — qaysi hodisa qaysi darajadan xabar qilinadi
- alert_history  — yuborilgan bildirishnomalar tarixi
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'alert_channels',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('type', sa.String(), nullable=False, server_default='telegram'),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('config_enc', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_table(
        'alert_rules',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('event_category', sa.String(), nullable=False, server_default='*'),
        sa.Column('min_severity', sa.String(), nullable=False, server_default='warning'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        'alert_history',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('severity', sa.String(), nullable=True),
        sa.Column('category', sa.String(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('raw_message', sa.Text(), nullable=True),
        sa.Column('channel_type', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('ai_used', sa.Boolean(), nullable=True, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_alert_history_severity', 'alert_history', ['severity'])
    op.create_index('ix_alert_history_category', 'alert_history', ['category'])
    op.create_index('ix_alert_history_status', 'alert_history', ['status'])
    op.create_index('ix_alert_history_created_at', 'alert_history', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_alert_history_created_at', table_name='alert_history')
    op.drop_index('ix_alert_history_status', table_name='alert_history')
    op.drop_index('ix_alert_history_category', table_name='alert_history')
    op.drop_index('ix_alert_history_severity', table_name='alert_history')
    op.drop_table('alert_history')
    op.drop_table('alert_rules')
    op.drop_table('alert_channels')
