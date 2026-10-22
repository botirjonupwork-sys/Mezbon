"""AI agent config JSON (restaurant)

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-07-17 12:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "c5d6e7f8a9b0"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("restaurants", sa.Column("ai_agent_config", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("restaurants", "ai_agent_config")
