from __future__ import annotations

from sqlalchemy import and_, or_, select

from app.models import AuditLog, ConfigProfile, ConversationSession, EvaluationRun, KnowledgeItem, RetrievalRequest
from app.request_context import RequestContext, get_request_context


def resolve_request_scope(request_context: RequestContext | None = None) -> RequestContext:
    return request_context or get_request_context()


def _scope_clause_for_columns(tenant_column, team_column, request_context: RequestContext):
    clauses = []
    if request_context.tenant_id:
        clauses.append(tenant_column == request_context.tenant_id)
    if request_context.team_id and team_column is not None:
        clauses.append(team_column == request_context.team_id)
    return and_(*clauses) if clauses else None


def apply_session_scope(statement, request_context: RequestContext | None = None):
    current_context = resolve_request_scope(request_context)
    clause = _scope_clause_for_columns(ConversationSession.tenant_id, ConversationSession.team_id, current_context)
    return statement.where(clause) if clause is not None else statement


def apply_knowledge_scope(statement, request_context: RequestContext | None = None):
    current_context = resolve_request_scope(request_context)
    clause = _scope_clause_for_columns(KnowledgeItem.tenant_id, KnowledgeItem.team_id, current_context)
    return statement.where(clause) if clause is not None else statement


def apply_retrieval_request_scope(statement, request_context: RequestContext | None = None):
    current_context = resolve_request_scope(request_context)
    session_scope = _scope_clause_for_columns(ConversationSession.tenant_id, ConversationSession.team_id, current_context)
    if session_scope is None:
        return statement
    scoped_session_ids = select(ConversationSession.session_id).where(session_scope)
    return statement.where(RetrievalRequest.session_id.in_(scoped_session_ids))


def apply_config_scope(statement, request_context: RequestContext | None = None):
    current_context = resolve_request_scope(request_context)
    clauses = [ConfigProfile.scope_type.in_(('global', 'repo', 'path'))]
    if not current_context.tenant_id:
        return statement.where(*clauses)
    tenant_scopes = [f'tenant:{current_context.tenant_id}']
    if current_context.team_id:
        tenant_scopes.append(f'team:{current_context.tenant_id}:{current_context.team_id}')
    clauses.append(
        or_(
            ConfigProfile.scope_type.in_(('global', 'repo', 'path')),
            and_(ConfigProfile.scope_type == 'tenant', ConfigProfile.scope_id == tenant_scopes[0]),
            and_(ConfigProfile.scope_type == 'team', ConfigProfile.scope_id.in_(tenant_scopes[1:] or ['__never__'])),
        )
    )
    return statement.where(*clauses)


def apply_audit_scope(statement, request_context: RequestContext | None = None):
    current_context = resolve_request_scope(request_context)
    clauses = []
    if current_context.tenant_id:
        clauses.append(AuditLog.detail['tenant_id'].as_string() == current_context.tenant_id)
    if current_context.team_id:
        clauses.append(AuditLog.detail['team_id'].as_string() == current_context.team_id)
    return statement.where(and_(*clauses)) if clauses else statement


def apply_evaluation_scope(statement, request_context: RequestContext | None = None):
    current_context = resolve_request_scope(request_context)
    clause = _scope_clause_for_columns(EvaluationRun.tenant_id, EvaluationRun.team_id, current_context)
    return statement.where(clause) if clause is not None else statement
