"""add vector index entry table

Revision ID: 20260326_0004
Revises: 20260326_0003
Create Date: 2026-03-26 12:20:00

"""

from alembic import op
import sqlalchemy as sa


revision = '20260326_0004'
down_revision = '20260326_0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'vector_index_entry',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('document_id', sa.String(length=160), nullable=False),
        sa.Column('entity_type', sa.String(length=32), nullable=False),
        sa.Column('entity_id', sa.String(length=64), nullable=False),
        sa.Column('tenant_id', sa.String(length=64), nullable=True),
        sa.Column('team_id', sa.String(length=64), nullable=True),
        sa.Column('scope_type', sa.String(length=32), nullable=True),
        sa.Column('scope_id', sa.String(length=128), nullable=True),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('embedding_model', sa.String(length=128), nullable=False),
        sa.Column('source_text', sa.Text(), nullable=False),
        sa.Column('vector', sa.JSON(), nullable=False),
        sa.Column('document_metadata', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_vector_index_entry_document_id', 'vector_index_entry', ['document_id'], unique=True)
    op.create_index('ix_vector_index_entry_entity_type', 'vector_index_entry', ['entity_type'])
    op.create_index('ix_vector_index_entry_entity_id', 'vector_index_entry', ['entity_id'])
    op.create_index('ix_vector_index_entry_tenant_id', 'vector_index_entry', ['tenant_id'])
    op.create_index('ix_vector_index_entry_team_id', 'vector_index_entry', ['team_id'])
    op.create_index('ix_vector_index_entry_scope_type', 'vector_index_entry', ['scope_type'])
    op.create_index('ix_vector_index_entry_scope_id', 'vector_index_entry', ['scope_id'])
    op.create_index('ix_vector_index_entry_content_hash', 'vector_index_entry', ['content_hash'])


def downgrade() -> None:
    op.drop_index('ix_vector_index_entry_content_hash', table_name='vector_index_entry')
    op.drop_index('ix_vector_index_entry_scope_id', table_name='vector_index_entry')
    op.drop_index('ix_vector_index_entry_scope_type', table_name='vector_index_entry')
    op.drop_index('ix_vector_index_entry_team_id', table_name='vector_index_entry')
    op.drop_index('ix_vector_index_entry_tenant_id', table_name='vector_index_entry')
    op.drop_index('ix_vector_index_entry_entity_id', table_name='vector_index_entry')
    op.drop_index('ix_vector_index_entry_entity_type', table_name='vector_index_entry')
    op.drop_index('ix_vector_index_entry_document_id', table_name='vector_index_entry')
    op.drop_table('vector_index_entry')
