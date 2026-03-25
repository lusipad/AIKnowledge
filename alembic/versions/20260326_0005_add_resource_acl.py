"""add resource acl columns

Revision ID: 20260326_0005
Revises: 20260326_0004
Create Date: 2026-03-26 14:10:00

"""

from alembic import op
import sqlalchemy as sa


revision = '20260326_0005'
down_revision = '20260326_0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'acl' not in {column['name'] for column in inspector.get_columns('knowledge_item')}:
        op.add_column('knowledge_item', sa.Column('acl', sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    if 'acl' not in {column['name'] for column in inspector.get_columns('config_profile')}:
        op.add_column('config_profile', sa.Column('acl', sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    if 'acl' not in {column['name'] for column in inspector.get_columns('config_profile_version')}:
        op.add_column('config_profile_version', sa.Column('acl', sa.JSON(), nullable=False, server_default=sa.text("'{}'")))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'acl' in {column['name'] for column in inspector.get_columns('config_profile_version')}:
        op.drop_column('config_profile_version', 'acl')
    if 'acl' in {column['name'] for column in inspector.get_columns('config_profile')}:
        op.drop_column('config_profile', 'acl')
    if 'acl' in {column['name'] for column in inspector.get_columns('knowledge_item')}:
        op.drop_column('knowledge_item', 'acl')
