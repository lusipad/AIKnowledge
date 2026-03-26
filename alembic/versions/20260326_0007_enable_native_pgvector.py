"""enable native pgvector storage

Revision ID: 20260326_0007
Revises: 20260326_0006
Create Date: 2026-03-26 19:00:00

"""

import os

from alembic import op
import sqlalchemy as sa


revision = '20260326_0007'
down_revision = '20260326_0006'
branch_labels = None
depends_on = None


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == 'postgresql'


def _vector_dimensions() -> int:
    return max(1, int(os.getenv('AICODING_VECTOR_DIMENSIONS', '1536')))


def _index_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {index['name'] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    if not _is_postgresql():
        return

    dimensions = _vector_dimensions()
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    op.execute(
        'ALTER TABLE vector_index_entry '
        f'ALTER COLUMN vector TYPE vector({dimensions}) '
        "USING replace(vector::text, ' ', '')::vector("
        f'{dimensions})'
    )

    if 'ix_vector_index_entry_vector_hnsw' not in _index_names('vector_index_entry'):
        op.execute(
            'CREATE INDEX ix_vector_index_entry_vector_hnsw '
            'ON vector_index_entry USING hnsw (vector vector_cosine_ops)'
        )


def downgrade() -> None:
    if not _is_postgresql():
        return

    if 'ix_vector_index_entry_vector_hnsw' in _index_names('vector_index_entry'):
        op.drop_index('ix_vector_index_entry_vector_hnsw', table_name='vector_index_entry')

    op.execute(
        'ALTER TABLE vector_index_entry '
        'ALTER COLUMN vector TYPE json '
        'USING vector::text::json'
    )
