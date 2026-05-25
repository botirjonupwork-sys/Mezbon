"""phase12 AI Agent extras

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-05-25 16:00:00.000000

Restaurant'ga AI Operator uchun qo'shimcha sozlamalar:
  + ai_agent_greeting        — kirish tabrigi ("Assalomu alaykum, ...")
  + ai_agent_work_hours_only — True bo'lsa faqat work_hours_from..until oraliqida javob beradi
  + ai_agent_max_call_minutes — bitta suhbatning max davomiyligi (xarajat nazorati)
  + ai_agent_fallback_phone  — AI tushunmasa shu raqamga uzatadi
  + ai_agent_language        — 'uz' | 'ru' | 'auto'

provider/model/api_key restoran jadvalida qoladi (eski ma'lumotlar uchun) lekin
artiq ishlatilmaydi — barchasi platform_settings'dan o'qiladi.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('restaurants', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ai_agent_greeting', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('ai_agent_work_hours_only', sa.Boolean(), nullable=True, server_default=sa.false()))
        batch_op.add_column(sa.Column('ai_agent_max_call_minutes', sa.Integer(), nullable=True, server_default=sa.text('10')))
        batch_op.add_column(sa.Column('ai_agent_fallback_phone', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('ai_agent_language', sa.String(), nullable=True, server_default=sa.text("'uz'")))


def downgrade() -> None:
    with op.batch_alter_table('restaurants', schema=None) as batch_op:
        batch_op.drop_column('ai_agent_language')
        batch_op.drop_column('ai_agent_fallback_phone')
        batch_op.drop_column('ai_agent_max_call_minutes')
        batch_op.drop_column('ai_agent_work_hours_only')
        batch_op.drop_column('ai_agent_greeting')
