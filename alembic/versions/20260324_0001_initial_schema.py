"""initial schema

Revision ID: 20260324_0001
Revises: None
Create Date: 2026-03-24 18:00:00

"""

from alembic import op
import sqlalchemy as sa


revision = '20260324_0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'conversation_session',
        sa.Column('session_id', sa.String(length=64), primary_key=True),
        sa.Column('tenant_id', sa.String(length=64), nullable=True),
        sa.Column('team_id', sa.String(length=64), nullable=True),
        sa.Column('user_id', sa.String(length=64), nullable=True),
        sa.Column('repo_id', sa.String(length=128), nullable=False),
        sa.Column('branch_name', sa.String(length=256), nullable=True),
        sa.Column('task_id', sa.String(length=128), nullable=True),
        sa.Column('client_type', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_conversation_session_repo_id', 'conversation_session', ['repo_id'])
    op.create_index('ix_conversation_session_task_id', 'conversation_session', ['task_id'])

    op.create_table(
        'knowledge_item',
        sa.Column('knowledge_id', sa.String(length=64), primary_key=True),
        sa.Column('tenant_id', sa.String(length=64), nullable=True),
        sa.Column('scope_type', sa.String(length=32), nullable=False),
        sa.Column('scope_id', sa.String(length=128), nullable=False),
        sa.Column('knowledge_type', sa.String(length=32), nullable=False),
        sa.Column('memory_type', sa.String(length=32), nullable=False),
        sa.Column('title', sa.String(length=256), nullable=False),
        sa.Column('content', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('quality_score', sa.Numeric(5, 4), nullable=False),
        sa.Column('confidence_score', sa.Numeric(5, 4), nullable=False),
        sa.Column('freshness_score', sa.Numeric(5, 4), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('effective_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('effective_to', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_knowledge_item_scope_type', 'knowledge_item', ['scope_type'])
    op.create_index('ix_knowledge_item_scope_id', 'knowledge_item', ['scope_id'])
    op.create_index('ix_knowledge_item_knowledge_type', 'knowledge_item', ['knowledge_type'])
    op.create_index('ix_knowledge_item_memory_type', 'knowledge_item', ['memory_type'])
    op.create_index('ix_knowledge_item_status', 'knowledge_item', ['status'])

    op.create_table(
        'config_profile',
        sa.Column('profile_id', sa.String(length=64), primary_key=True),
        sa.Column('scope_type', sa.String(length=32), nullable=False),
        sa.Column('scope_id', sa.String(length=128), nullable=False),
        sa.Column('profile_type', sa.String(length=32), nullable=False),
        sa.Column('content', sa.JSON(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_config_profile_scope_type', 'config_profile', ['scope_type'])
    op.create_index('ix_config_profile_scope_id', 'config_profile', ['scope_id'])
    op.create_index('ix_config_profile_profile_type', 'config_profile', ['profile_type'])
    op.create_index('ix_config_profile_status', 'config_profile', ['status'])

    op.create_table(
        'config_profile_version',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('profile_id', sa.String(length=64), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('content', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_config_profile_version_profile_id', 'config_profile_version', ['profile_id'])

    op.create_table(
        'session_event',
        sa.Column('event_id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('session_id', sa.String(length=64), sa.ForeignKey('conversation_session.session_id'), nullable=False),
        sa.Column('event_type', sa.String(length=32), nullable=False),
        sa.Column('event_subtype', sa.String(length=64), nullable=True),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('content_ref', sa.String(length=256), nullable=True),
        sa.Column('tool_name', sa.String(length=64), nullable=True),
        sa.Column('file_paths', sa.JSON(), nullable=False),
        sa.Column('symbol_names', sa.JSON(), nullable=False),
        sa.Column('event_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_session_event_session_id', 'session_event', ['session_id'])
    op.create_index('ix_session_event_event_type', 'session_event', ['event_type'])
    op.create_index('ix_session_event_event_time', 'session_event', ['event_time'])

    op.create_table(
        'knowledge_signal',
        sa.Column('signal_id', sa.String(length=64), primary_key=True),
        sa.Column('session_id', sa.String(length=64), sa.ForeignKey('conversation_session.session_id'), nullable=False),
        sa.Column('signal_type', sa.String(length=32), nullable=False),
        sa.Column('confidence', sa.Numeric(5, 4), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('source_refs', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_knowledge_signal_session_id', 'knowledge_signal', ['session_id'])
    op.create_index('ix_knowledge_signal_signal_type', 'knowledge_signal', ['signal_type'])

    op.create_table(
        'knowledge_candidate',
        sa.Column('candidate_id', sa.String(length=64), primary_key=True),
        sa.Column('signal_id', sa.String(length=64), sa.ForeignKey('knowledge_signal.signal_id'), nullable=False),
        sa.Column('candidate_type', sa.String(length=32), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('scope_hint', sa.JSON(), nullable=False),
        sa.Column('quality_score', sa.Numeric(5, 4), nullable=False),
        sa.Column('extract_prompt_version', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_knowledge_candidate_signal_id', 'knowledge_candidate', ['signal_id'])

    op.create_table(
        'knowledge_source_ref',
        sa.Column('ref_id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('knowledge_id', sa.String(length=64), sa.ForeignKey('knowledge_item.knowledge_id'), nullable=False),
        sa.Column('ref_type', sa.String(length=32), nullable=False),
        sa.Column('ref_target_id', sa.String(length=128), nullable=True),
        sa.Column('ref_path', sa.String(length=512), nullable=True),
        sa.Column('ref_commit', sa.String(length=64), nullable=True),
        sa.Column('ref_pr', sa.String(length=64), nullable=True),
        sa.Column('ref_issue', sa.String(length=64), nullable=True),
        sa.Column('excerpt_summary', sa.Text(), nullable=True),
    )
    op.create_index('ix_knowledge_source_ref_knowledge_id', 'knowledge_source_ref', ['knowledge_id'])

    op.create_table(
        'extract_task',
        sa.Column('task_id', sa.String(length=64), primary_key=True),
        sa.Column('candidate_id', sa.String(length=64), sa.ForeignKey('knowledge_candidate.candidate_id'), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('model_name', sa.String(length=64), nullable=False),
        sa.Column('prompt_version', sa.String(length=32), nullable=False),
        sa.Column('result_ref', sa.String(length=256), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_extract_task_candidate_id', 'extract_task', ['candidate_id'])

    op.create_table(
        'knowledge_review',
        sa.Column('review_id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('knowledge_id', sa.String(length=64), sa.ForeignKey('knowledge_item.knowledge_id'), nullable=False),
        sa.Column('reviewer_id', sa.String(length=64), nullable=False),
        sa.Column('decision', sa.String(length=16), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_knowledge_review_knowledge_id', 'knowledge_review', ['knowledge_id'])

    op.create_table(
        'retrieval_request',
        sa.Column('request_id', sa.String(length=64), primary_key=True),
        sa.Column('session_id', sa.String(length=64), nullable=False),
        sa.Column('query_text', sa.Text(), nullable=False),
        sa.Column('query_type', sa.String(length=32), nullable=False),
        sa.Column('repo_id', sa.String(length=128), nullable=True),
        sa.Column('branch_name', sa.String(length=256), nullable=True),
        sa.Column('file_paths', sa.JSON(), nullable=False),
        sa.Column('token_budget', sa.Integer(), nullable=False),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_retrieval_request_session_id', 'retrieval_request', ['session_id'])
    op.create_index('ix_retrieval_request_repo_id', 'retrieval_request', ['repo_id'])

    op.create_table(
        'retrieval_result',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('request_id', sa.String(length=64), sa.ForeignKey('retrieval_request.request_id'), nullable=False),
        sa.Column('knowledge_id', sa.String(length=64), nullable=False),
        sa.Column('recall_channel', sa.String(length=32), nullable=False),
        sa.Column('recall_score', sa.Numeric(8, 6), nullable=False),
        sa.Column('rerank_score', sa.Numeric(8, 6), nullable=False),
        sa.Column('selected', sa.Boolean(), nullable=False),
        sa.Column('selected_rank', sa.Integer(), nullable=True),
    )
    op.create_index('ix_retrieval_result_request_id', 'retrieval_result', ['request_id'])
    op.create_index('ix_retrieval_result_knowledge_id', 'retrieval_result', ['knowledge_id'])

    op.create_table(
        'knowledge_feedback',
        sa.Column('feedback_id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('knowledge_id', sa.String(length=64), sa.ForeignKey('knowledge_item.knowledge_id'), nullable=False),
        sa.Column('request_id', sa.String(length=64), nullable=True),
        sa.Column('feedback_type', sa.String(length=32), nullable=False),
        sa.Column('feedback_score', sa.Integer(), nullable=False),
        sa.Column('feedback_text', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_knowledge_feedback_knowledge_id', 'knowledge_feedback', ['knowledge_id'])
    op.create_index('ix_knowledge_feedback_request_id', 'knowledge_feedback', ['request_id'])

    op.create_table(
        'context_pack_feedback',
        sa.Column('feedback_id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('request_id', sa.String(length=64), nullable=False),
        sa.Column('feedback_score', sa.Integer(), nullable=False),
        sa.Column('relevance_score', sa.Integer(), nullable=True),
        sa.Column('completeness_score', sa.Integer(), nullable=True),
        sa.Column('feedback_text', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_context_pack_feedback_request_id', 'context_pack_feedback', ['request_id'])

    op.create_table(
        'audit_log',
        sa.Column('audit_id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('actor_id', sa.String(length=64), nullable=False),
        sa.Column('action', sa.String(length=64), nullable=False),
        sa.Column('resource_type', sa.String(length=32), nullable=False),
        sa.Column('resource_id', sa.String(length=64), nullable=False),
        sa.Column('scope_type', sa.String(length=32), nullable=True),
        sa.Column('scope_id', sa.String(length=128), nullable=True),
        sa.Column('detail', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_audit_log_action', 'audit_log', ['action'])
    op.create_index('ix_audit_log_resource_type', 'audit_log', ['resource_type'])
    op.create_index('ix_audit_log_resource_id', 'audit_log', ['resource_id'])
    op.create_index('ix_audit_log_scope_type', 'audit_log', ['scope_type'])
    op.create_index('ix_audit_log_scope_id', 'audit_log', ['scope_id'])
    op.create_index('ix_audit_log_created_at', 'audit_log', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_audit_log_created_at', table_name='audit_log')
    op.drop_index('ix_audit_log_scope_id', table_name='audit_log')
    op.drop_index('ix_audit_log_scope_type', table_name='audit_log')
    op.drop_index('ix_audit_log_resource_id', table_name='audit_log')
    op.drop_index('ix_audit_log_resource_type', table_name='audit_log')
    op.drop_index('ix_audit_log_action', table_name='audit_log')
    op.drop_table('audit_log')

    op.drop_index('ix_context_pack_feedback_request_id', table_name='context_pack_feedback')
    op.drop_table('context_pack_feedback')

    op.drop_index('ix_knowledge_feedback_request_id', table_name='knowledge_feedback')
    op.drop_index('ix_knowledge_feedback_knowledge_id', table_name='knowledge_feedback')
    op.drop_table('knowledge_feedback')

    op.drop_index('ix_retrieval_result_knowledge_id', table_name='retrieval_result')
    op.drop_index('ix_retrieval_result_request_id', table_name='retrieval_result')
    op.drop_table('retrieval_result')

    op.drop_index('ix_retrieval_request_repo_id', table_name='retrieval_request')
    op.drop_index('ix_retrieval_request_session_id', table_name='retrieval_request')
    op.drop_table('retrieval_request')

    op.drop_index('ix_knowledge_review_knowledge_id', table_name='knowledge_review')
    op.drop_table('knowledge_review')

    op.drop_index('ix_extract_task_candidate_id', table_name='extract_task')
    op.drop_table('extract_task')

    op.drop_index('ix_knowledge_source_ref_knowledge_id', table_name='knowledge_source_ref')
    op.drop_table('knowledge_source_ref')

    op.drop_index('ix_knowledge_candidate_signal_id', table_name='knowledge_candidate')
    op.drop_table('knowledge_candidate')

    op.drop_index('ix_knowledge_signal_signal_type', table_name='knowledge_signal')
    op.drop_index('ix_knowledge_signal_session_id', table_name='knowledge_signal')
    op.drop_table('knowledge_signal')

    op.drop_index('ix_session_event_event_time', table_name='session_event')
    op.drop_index('ix_session_event_event_type', table_name='session_event')
    op.drop_index('ix_session_event_session_id', table_name='session_event')
    op.drop_table('session_event')

    op.drop_index('ix_config_profile_version_profile_id', table_name='config_profile_version')
    op.drop_table('config_profile_version')

    op.drop_index('ix_config_profile_status', table_name='config_profile')
    op.drop_index('ix_config_profile_profile_type', table_name='config_profile')
    op.drop_index('ix_config_profile_scope_id', table_name='config_profile')
    op.drop_index('ix_config_profile_scope_type', table_name='config_profile')
    op.drop_table('config_profile')

    op.drop_index('ix_knowledge_item_status', table_name='knowledge_item')
    op.drop_index('ix_knowledge_item_memory_type', table_name='knowledge_item')
    op.drop_index('ix_knowledge_item_knowledge_type', table_name='knowledge_item')
    op.drop_index('ix_knowledge_item_scope_id', table_name='knowledge_item')
    op.drop_index('ix_knowledge_item_scope_type', table_name='knowledge_item')
    op.drop_table('knowledge_item')

    op.drop_index('ix_conversation_session_task_id', table_name='conversation_session')
    op.drop_index('ix_conversation_session_repo_id', table_name='conversation_session')
    op.drop_table('conversation_session')
