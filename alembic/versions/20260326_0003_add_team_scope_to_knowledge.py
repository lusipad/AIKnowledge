"""add team scope to knowledge item

Revision ID: 20260326_0003
Revises: 20260325_0002
Create Date: 2026-03-26 11:30:00

"""

from alembic import op
import sqlalchemy as sa


revision = '20260326_0003'
down_revision = '20260325_0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('knowledge_item', sa.Column('team_id', sa.String(length=64), nullable=True))
    op.create_index('ix_knowledge_item_team_id', 'knowledge_item', ['team_id'])


def downgrade() -> None:
    op.drop_index('ix_knowledge_item_team_id', table_name='knowledge_item')
    op.drop_column('knowledge_item', 'team_id')
