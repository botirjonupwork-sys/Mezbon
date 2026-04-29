"""add super admin actions

Revision ID: 3b969d8e6afd
Revises: 2275d52643cd
Create Date: 2026-04-29 13:00:35.600744

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3b969d8e6afd'
down_revision: Union[str, None] = '2275d52643cd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'super_admin_actions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('actor', sa.String(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('target_type', sa.String(), nullable=True),
        sa.Column('target_id', sa.Integer(), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('ip', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('super_admin_actions')
