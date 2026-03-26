"""add knowledge relation graph

Revision ID: 20260326_0009
Revises: 20260326_0008
Create Date: 2026-03-26 23:35:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '20260326_0009'
down_revision = '20260326_0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'knowledge_relation',
        sa.Column('relation_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.String(length=64), nullable=True),
        sa.Column('team_id', sa.String(length=64), nullable=True),
        sa.Column('repo_id', sa.String(length=128), nullable=False),
        sa.Column('related_repo_id', sa.String(length=128), nullable=False),
        sa.Column('knowledge_id', sa.String(length=64), nullable=False),
        sa.Column('related_knowledge_id', sa.String(length=64), nullable=False),
        sa.Column('relation_type', sa.String(length=32), nullable=False),
        sa.Column('weight', sa.Numeric(5, 4), nullable=False),
        sa.Column('detail', sa.JSON(), nullable=False),
        sa.Column('created_by', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['knowledge_id'], ['knowledge_item.knowledge_id']),
        sa.ForeignKeyConstraint(['related_knowledge_id'], ['knowledge_item.knowledge_id']),
        sa.PrimaryKeyConstraint('relation_id'),
    )
    op.create_index(op.f('ix_knowledge_relation_knowledge_id'), 'knowledge_relation', ['knowledge_id'], unique=False)
    op.create_index(op.f('ix_knowledge_relation_related_knowledge_id'), 'knowledge_relation', ['related_knowledge_id'], unique=False)
    op.create_index(op.f('ix_knowledge_relation_relation_type'), 'knowledge_relation', ['relation_type'], unique=False)
    op.create_index(op.f('ix_knowledge_relation_related_repo_id'), 'knowledge_relation', ['related_repo_id'], unique=False)
    op.create_index(op.f('ix_knowledge_relation_repo_id'), 'knowledge_relation', ['repo_id'], unique=False)
    op.create_index(op.f('ix_knowledge_relation_team_id'), 'knowledge_relation', ['team_id'], unique=False)
    op.create_index(op.f('ix_knowledge_relation_tenant_id'), 'knowledge_relation', ['tenant_id'], unique=False)
    op.create_index('ix_knowledge_relation_edge', 'knowledge_relation', ['knowledge_id', 'related_knowledge_id', 'relation_type'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_knowledge_relation_edge', table_name='knowledge_relation')
    op.drop_index(op.f('ix_knowledge_relation_tenant_id'), table_name='knowledge_relation')
    op.drop_index(op.f('ix_knowledge_relation_team_id'), table_name='knowledge_relation')
    op.drop_index(op.f('ix_knowledge_relation_repo_id'), table_name='knowledge_relation')
    op.drop_index(op.f('ix_knowledge_relation_related_repo_id'), table_name='knowledge_relation')
    op.drop_index(op.f('ix_knowledge_relation_relation_type'), table_name='knowledge_relation')
    op.drop_index(op.f('ix_knowledge_relation_related_knowledge_id'), table_name='knowledge_relation')
    op.drop_index(op.f('ix_knowledge_relation_knowledge_id'), table_name='knowledge_relation')
    op.drop_table('knowledge_relation')
