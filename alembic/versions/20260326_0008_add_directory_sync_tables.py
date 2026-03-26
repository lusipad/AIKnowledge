"""add directory sync tables

Revision ID: 20260326_0008
Revises: 20260326_0007
Create Date: 2026-03-26 20:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '20260326_0008'
down_revision = '20260326_0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'directory_user',
        sa.Column('user_id', sa.String(length=64), nullable=False),
        sa.Column('tenant_id', sa.String(length=64), nullable=True),
        sa.Column('team_id', sa.String(length=64), nullable=True),
        sa.Column('external_ref', sa.String(length=128), nullable=True),
        sa.Column('email', sa.String(length=256), nullable=True),
        sa.Column('display_name', sa.String(length=256), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('attributes', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('user_id'),
        sa.UniqueConstraint('external_ref'),
    )
    op.create_index(op.f('ix_directory_user_active'), 'directory_user', ['active'], unique=False)
    op.create_index(op.f('ix_directory_user_email'), 'directory_user', ['email'], unique=False)
    op.create_index(op.f('ix_directory_user_team_id'), 'directory_user', ['team_id'], unique=False)
    op.create_index(op.f('ix_directory_user_tenant_id'), 'directory_user', ['tenant_id'], unique=False)

    op.create_table(
        'directory_group',
        sa.Column('group_id', sa.String(length=64), nullable=False),
        sa.Column('tenant_id', sa.String(length=64), nullable=True),
        sa.Column('team_id', sa.String(length=64), nullable=True),
        sa.Column('external_ref', sa.String(length=128), nullable=True),
        sa.Column('display_name', sa.String(length=256), nullable=False),
        sa.Column('scope_type', sa.String(length=16), nullable=False),
        sa.Column('scope_id', sa.String(length=128), nullable=False),
        sa.Column('mapped_role', sa.String(length=16), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('attributes', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('group_id'),
        sa.UniqueConstraint('external_ref'),
    )
    op.create_index(op.f('ix_directory_group_active'), 'directory_group', ['active'], unique=False)
    op.create_index(op.f('ix_directory_group_mapped_role'), 'directory_group', ['mapped_role'], unique=False)
    op.create_index(op.f('ix_directory_group_scope_id'), 'directory_group', ['scope_id'], unique=False)
    op.create_index(op.f('ix_directory_group_scope_type'), 'directory_group', ['scope_type'], unique=False)
    op.create_index(op.f('ix_directory_group_team_id'), 'directory_group', ['team_id'], unique=False)
    op.create_index(op.f('ix_directory_group_tenant_id'), 'directory_group', ['tenant_id'], unique=False)

    op.create_table(
        'directory_group_membership',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('group_id', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['group_id'], ['directory_group.group_id']),
        sa.ForeignKeyConstraint(['user_id'], ['directory_user.user_id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_directory_group_membership_group_id'), 'directory_group_membership', ['group_id'], unique=False)
    op.create_index(op.f('ix_directory_group_membership_user_id'), 'directory_group_membership', ['user_id'], unique=False)
    op.create_index('ix_directory_group_membership_group_user', 'directory_group_membership', ['group_id', 'user_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_directory_group_membership_group_user', table_name='directory_group_membership')
    op.drop_index(op.f('ix_directory_group_membership_user_id'), table_name='directory_group_membership')
    op.drop_index(op.f('ix_directory_group_membership_group_id'), table_name='directory_group_membership')
    op.drop_table('directory_group_membership')
    op.drop_index(op.f('ix_directory_group_tenant_id'), table_name='directory_group')
    op.drop_index(op.f('ix_directory_group_team_id'), table_name='directory_group')
    op.drop_index(op.f('ix_directory_group_scope_type'), table_name='directory_group')
    op.drop_index(op.f('ix_directory_group_scope_id'), table_name='directory_group')
    op.drop_index(op.f('ix_directory_group_mapped_role'), table_name='directory_group')
    op.drop_index(op.f('ix_directory_group_active'), table_name='directory_group')
    op.drop_table('directory_group')
    op.drop_index(op.f('ix_directory_user_tenant_id'), table_name='directory_user')
    op.drop_index(op.f('ix_directory_user_team_id'), table_name='directory_user')
    op.drop_index(op.f('ix_directory_user_email'), table_name='directory_user')
    op.drop_index(op.f('ix_directory_user_active'), table_name='directory_user')
    op.drop_table('directory_user')
