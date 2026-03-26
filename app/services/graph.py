from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import KnowledgeItem, KnowledgeRelation
from app.request_context import RequestContext
from app.services.isolation import apply_graph_relation_scope, apply_knowledge_scope
from app.services.resource_acl import can_review_resource, can_view_resource


ALLOWED_RELATION_TYPES = {'related_to', 'implements_rule', 'supersedes', 'same_incident_family'}


class KnowledgeGraphError(ValueError):
    pass


def _serialize_knowledge_node(knowledge: KnowledgeItem) -> dict:
    return {
        'knowledge_id': knowledge.knowledge_id,
        'tenant_id': knowledge.tenant_id,
        'team_id': knowledge.team_id,
        'scope_type': knowledge.scope_type,
        'scope_id': knowledge.scope_id,
        'knowledge_type': knowledge.knowledge_type,
        'memory_type': knowledge.memory_type,
        'title': knowledge.title,
        'status': knowledge.status,
        'acl': knowledge.acl,
        'updated_at': knowledge.updated_at.isoformat(),
    }


def _normalize_relation_type(relation_type: str) -> str:
    normalized = relation_type.strip().lower()
    if normalized not in ALLOWED_RELATION_TYPES:
        raise KnowledgeGraphError(f'unsupported relation_type: {relation_type}')
    return normalized


def _resolve_repo_id(knowledge: KnowledgeItem, explicit_repo_id: str | None) -> str:
    if explicit_repo_id:
        return explicit_repo_id
    if knowledge.scope_type == 'repo':
        return knowledge.scope_id
    if isinstance(knowledge.content, dict):
        for key in ('repo_id', 'repo'):
            value = knowledge.content.get(key)
            if value:
                return str(value)
    raise KnowledgeGraphError(f'knowledge {knowledge.knowledge_id} requires explicit repo_id for graph relations')


def _load_graph_knowledge(database: Session, knowledge_id: str, request_context: RequestContext) -> KnowledgeItem:
    knowledge = database.scalar(apply_knowledge_scope(select(KnowledgeItem).where(KnowledgeItem.knowledge_id == knowledge_id), request_context))
    if not knowledge or not can_view_resource(knowledge.acl, request_context):
        raise KnowledgeGraphError(f'knowledge not found: {knowledge_id}')
    return knowledge


def upsert_knowledge_relation(database: Session, payload, request_context: RequestContext) -> dict:
    if payload.knowledge_id == payload.related_knowledge_id:
        raise KnowledgeGraphError('knowledge relation endpoints do not support self-references')

    knowledge = _load_graph_knowledge(database, payload.knowledge_id, request_context)
    related_knowledge = _load_graph_knowledge(database, payload.related_knowledge_id, request_context)
    if not can_review_resource(knowledge.acl, request_context) or not can_review_resource(related_knowledge.acl, request_context):
        raise KnowledgeGraphError('knowledge relation requires reviewer access to both knowledge items')

    relation_type = _normalize_relation_type(payload.relation_type)
    repo_id = _resolve_repo_id(knowledge, payload.repo_id)
    related_repo_id = _resolve_repo_id(related_knowledge, payload.related_repo_id)

    relation = database.scalar(
        apply_graph_relation_scope(
            select(KnowledgeRelation).where(
                KnowledgeRelation.knowledge_id == payload.knowledge_id,
                KnowledgeRelation.related_knowledge_id == payload.related_knowledge_id,
                KnowledgeRelation.relation_type == relation_type,
            ),
            request_context,
        )
    )
    if relation is None:
        relation = KnowledgeRelation(
            knowledge_id=payload.knowledge_id,
            related_knowledge_id=payload.related_knowledge_id,
            relation_type=relation_type,
        )
        database.add(relation)

    relation.tenant_id = request_context.tenant_id or knowledge.tenant_id
    relation.team_id = request_context.team_id or knowledge.team_id
    relation.repo_id = repo_id
    relation.related_repo_id = related_repo_id
    relation.weight = max(0.0, min(float(payload.weight), 1.0))
    relation.detail = dict(payload.detail)
    relation.created_by = request_context.user_id or 'system'
    database.flush()
    return serialize_relation(relation)


def serialize_relation(relation: KnowledgeRelation) -> dict:
    return {
        'relation_id': relation.relation_id,
        'tenant_id': relation.tenant_id,
        'team_id': relation.team_id,
        'repo_id': relation.repo_id,
        'related_repo_id': relation.related_repo_id,
        'knowledge_id': relation.knowledge_id,
        'related_knowledge_id': relation.related_knowledge_id,
        'relation_type': relation.relation_type,
        'weight': float(relation.weight),
        'detail': relation.detail,
        'created_by': relation.created_by,
        'created_at': relation.created_at.isoformat(),
        'updated_at': relation.updated_at.isoformat(),
    }


def get_knowledge_graph(database: Session, knowledge_id: str, request_context: RequestContext) -> dict:
    center = _load_graph_knowledge(database, knowledge_id, request_context)
    relations = database.scalars(
        apply_graph_relation_scope(
            select(KnowledgeRelation).where(
                or_(
                    KnowledgeRelation.knowledge_id == knowledge_id,
                    KnowledgeRelation.related_knowledge_id == knowledge_id,
                )
            ),
            request_context,
        )
    ).all()
    related_ids = {
        relation.knowledge_id if relation.knowledge_id != knowledge_id else relation.related_knowledge_id
        for relation in relations
    }
    related_items = {
        item.knowledge_id: item
        for item in database.scalars(
            apply_knowledge_scope(select(KnowledgeItem).where(KnowledgeItem.knowledge_id.in_(related_ids)), request_context)
        ).all()
        if can_view_resource(item.acl, request_context)
    }

    edges: list[dict] = []
    for relation in relations:
        counterpart_id = relation.related_knowledge_id if relation.knowledge_id == knowledge_id else relation.knowledge_id
        counterpart = related_items.get(counterpart_id)
        if counterpart is None:
            continue
        edges.append(
            {
                **serialize_relation(relation),
                'direction': 'outbound' if relation.knowledge_id == knowledge_id else 'inbound',
                'counterpart': _serialize_knowledge_node(counterpart),
            }
        )

    return {
        'knowledge': _serialize_knowledge_node(center),
        'connected_nodes': [_serialize_knowledge_node(item) for item in related_items.values()],
        'relations': edges,
    }


def get_repo_knowledge_map(database: Session, repo_id: str, request_context: RequestContext) -> dict:
    relations = database.scalars(
        apply_graph_relation_scope(
            select(KnowledgeRelation).where(
                or_(KnowledgeRelation.repo_id == repo_id, KnowledgeRelation.related_repo_id == repo_id)
            ),
            request_context,
        ).order_by(KnowledgeRelation.updated_at.desc())
    ).all()

    knowledge_ids = {
        item_id
        for relation in relations
        for item_id in (relation.knowledge_id, relation.related_knowledge_id)
    }
    visible_items = {
        item.knowledge_id: item
        for item in database.scalars(
            apply_knowledge_scope(select(KnowledgeItem).where(KnowledgeItem.knowledge_id.in_(knowledge_ids)), request_context)
        ).all()
        if can_view_resource(item.acl, request_context)
    }

    visible_relations = [
        serialize_relation(relation)
        for relation in relations
        if relation.knowledge_id in visible_items and relation.related_knowledge_id in visible_items
    ]
    return {
        'repo_id': repo_id,
        'nodes': [_serialize_knowledge_node(item) for item in visible_items.values()],
        'relations': visible_relations,
    }
