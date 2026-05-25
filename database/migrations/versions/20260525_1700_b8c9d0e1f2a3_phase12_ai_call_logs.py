"""phase12 AI call logs

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-05-25 17:00:00.000000

`ai_call_logs` jadvali — har bir AI suhbat haqida metadata + xarajat.

Kuzatiladigan ma'lumot:
  - call_id (Telegram uchun "tg:{chat_id}", Vapi uchun providerning call ID)
  - restaurant_id, user_phone, started_at, ended_at, duration_seconds
  - message_count          — qancha turn
  - tokens_in / tokens_out — LLM token sarfi
  - stt_seconds            — Whisper'dan o'tgan audio davomiyligi
  - tts_chars              — TTS'ga yuborilgan belgilar soni
  - cost_usd               — taxminiy xarajat (LLM + STT + TTS)
  - transcript             — JSON list: [{role, content, time}]
  - order_id               — buyurtma yaratildimi
  - ended_reason           — confirmed / transferred / time_limit / outside_hours / user_hangup
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ai_call_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('call_id', sa.String(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=False),
        sa.Column('user_phone', sa.String(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('message_count', sa.Integer(), nullable=True, server_default=sa.text('0')),
        sa.Column('tokens_in', sa.Integer(), nullable=True, server_default=sa.text('0')),
        sa.Column('tokens_out', sa.Integer(), nullable=True, server_default=sa.text('0')),
        sa.Column('stt_seconds', sa.Float(), nullable=True, server_default=sa.text('0')),
        sa.Column('tts_chars', sa.Integer(), nullable=True, server_default=sa.text('0')),
        sa.Column('cost_usd', sa.Float(), nullable=True, server_default=sa.text('0')),
        sa.Column('transcript', sa.Text(), nullable=True),     # JSON serialized
        sa.Column('order_id', sa.Integer(), nullable=True),
        sa.Column('ended_reason', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id']),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id']),
    )
    op.create_index('ix_ai_call_logs_restaurant_id', 'ai_call_logs', ['restaurant_id'])
    op.create_index('ix_ai_call_logs_started_at', 'ai_call_logs', ['started_at'])
    op.create_index('ix_ai_call_logs_call_id', 'ai_call_logs', ['call_id'])


def downgrade() -> None:
    op.drop_index('ix_ai_call_logs_call_id', table_name='ai_call_logs')
    op.drop_index('ix_ai_call_logs_started_at', table_name='ai_call_logs')
    op.drop_index('ix_ai_call_logs_restaurant_id', table_name='ai_call_logs')
    op.drop_table('ai_call_logs')
