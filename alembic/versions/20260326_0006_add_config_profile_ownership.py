"""add tenant ownership to config profiles

Revision ID: 20260326_0006
Revises: 20260326_0005
Create Date: 2026-03-26 16:00:00

"""

from alembic import op
import sqlalchemy as sa


revision = '20260326_0006'
down_revision = '20260326_0005'
branch_labels = None
depends_on = None


def _column_names(inspector, table_name: str) -> set[str]:
    return {column['name'] for column in inspector.get_columns(table_name)}


def _index_names(inspector, table_name: str) -> set[str]:
    return {index['name'] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    config_profile_columns = _column_names(inspector, 'config_profile')
    if 'tenant_id' not in config_profile_columns:
        op.add_column('config_profile', sa.Column('tenant_id', sa.String(length=64), nullable=True))
    if 'team_id' not in config_profile_columns:
        op.add_column('config_profile', sa.Column('team_id', sa.String(length=64), nullable=True))

    config_profile_indexes = _index_names(inspector, 'config_profile')
    if 'ix_config_profile_tenant_id' not in config_profile_indexes:
        op.create_index('ix_config_profile_tenant_id', 'config_profile', ['tenant_id'])
    if 'ix_config_profile_team_id' not in config_profile_indexes:
        op.create_index('ix_config_profile_team_id', 'config_profile', ['team_id'])

    config_profile_version_columns = _column_names(inspector, 'config_profile_version')
    if 'tenant_id' not in config_profile_version_columns:
        op.add_column('config_profile_version', sa.Column('tenant_id', sa.String(length=64), nullable=True))
    if 'team_id' not in config_profile_version_columns:
        op.add_column('config_profile_version', sa.Column('team_id', sa.String(length=64), nullable=True))

    config_profile_version_indexes = _index_names(inspector, 'config_profile_version')
    if 'ix_config_profile_version_tenant_id' not in config_profile_version_indexes:
        op.create_index('ix_config_profile_version_tenant_id', 'config_profile_version', ['tenant_id'])
    if 'ix_config_profile_version_team_id' not in config_profile_version_indexes:
        op.create_index('ix_config_profile_version_team_id', 'config_profile_version', ['team_id'])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    config_profile_version_indexes = _index_names(inspector, 'config_profile_version')
    if 'ix_config_profile_version_team_id' in config_profile_version_indexes:
        op.drop_index('ix_config_profile_version_team_id', table_name='config_profile_version')
    if 'ix_config_profile_version_tenant_id' in config_profile_version_indexes:
        op.drop_index('ix_config_profile_version_tenant_id', table_name='config_profile_version')

    config_profile_version_columns = _column_names(inspector, 'config_profile_version')
    if 'team_id' in config_profile_version_columns:
        op.drop_column('config_profile_version', 'team_id')
    if 'tenant_id' in config_profile_version_columns:
        op.drop_column('config_profile_version', 'tenant_id')

    config_profile_indexes = _index_names(inspector, 'config_profile')
    if 'ix_config_profile_team_id' in config_profile_indexes:
        op.drop_index('ix_config_profile_team_id', table_name='config_profile')
    if 'ix_config_profile_tenant_id' in config_profile_indexes:
        op.drop_index('ix_config_profile_tenant_id', table_name='config_profile')

    config_profile_columns = _column_names(inspector, 'config_profile')
    if 'team_id' in config_profile_columns:
        op.drop_column('config_profile', 'team_id')
    if 'tenant_id' in config_profile_columns:
        op.drop_column('config_profile', 'tenant_id')
