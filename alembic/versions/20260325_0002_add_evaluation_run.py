"""add evaluation run table

Revision ID: 20260325_0002
Revises: 20260324_0001
Create Date: 2026-03-25 10:40:00

"""

from alembic import op
import sqlalchemy as sa


revision = '20260325_0002'
down_revision = '20260324_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'evaluation_run',
        sa.Column('run_id', sa.String(length=64), primary_key=True),
        sa.Column('tenant_id', sa.String(length=64), nullable=True),
        sa.Column('team_id', sa.String(length=64), nullable=True),
        sa.Column('user_id', sa.String(length=64), nullable=True),
        sa.Column('scenario_id', sa.String(length=64), nullable=False),
        sa.Column('mode', sa.String(length=16), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('score', sa.Numeric(6, 2), nullable=False),
        sa.Column('passed_checks', sa.Integer(), nullable=False),
        sa.Column('total_checks', sa.Integer(), nullable=False),
        sa.Column('report', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_evaluation_run_tenant_id', 'evaluation_run', ['tenant_id'])
    op.create_index('ix_evaluation_run_team_id', 'evaluation_run', ['team_id'])
    op.create_index('ix_evaluation_run_user_id', 'evaluation_run', ['user_id'])
    op.create_index('ix_evaluation_run_scenario_id', 'evaluation_run', ['scenario_id'])
    op.create_index('ix_evaluation_run_status', 'evaluation_run', ['status'])
    op.create_index('ix_evaluation_run_created_at', 'evaluation_run', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_evaluation_run_created_at', table_name='evaluation_run')
    op.drop_index('ix_evaluation_run_status', table_name='evaluation_run')
    op.drop_index('ix_evaluation_run_scenario_id', table_name='evaluation_run')
    op.drop_index('ix_evaluation_run_user_id', table_name='evaluation_run')
    op.drop_index('ix_evaluation_run_team_id', table_name='evaluation_run')
    op.drop_index('ix_evaluation_run_tenant_id', table_name='evaluation_run')
    op.drop_table('evaluation_run')
