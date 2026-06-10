"""phase15 Payme Subscribe autopay — payme_cards jadvali + restaurants.autopay_enabled

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-06-02 12:00:00.000000

Roadmap Faza 15: restoran obunalarini avtomatik undirish (Payme Subscribe API).
Karta tokeni payme_cards.token_enc da SHIFRLANGAN holda saqlanadi (Fernet).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'payme_cards',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=False),
        sa.Column('token_enc', sa.Text(), nullable=False),
        sa.Column('card_last4', sa.String(), nullable=True),
        sa.Column('card_expire', sa.String(), nullable=True),
        sa.Column('verified', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_payme_cards_restaurant_id', 'payme_cards', ['restaurant_id'])

    with op.batch_alter_table('restaurants', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'autopay_enabled', sa.Boolean(), nullable=False, server_default=sa.text('0')
        ))


def downgrade() -> None:
    with op.batch_alter_table('restaurants', schema=None) as batch_op:
        batch_op.drop_column('autopay_enabled')

    op.drop_index('ix_payme_cards_restaurant_id', table_name='payme_cards')
    op.drop_table('payme_cards')
