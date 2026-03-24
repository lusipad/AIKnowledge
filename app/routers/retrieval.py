from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import ConfigProfile, KnowledgeItem, RetrievalRequest, RetrievalResult
from app.schemas import RetrievalQueryRequest
from app.services.audit import append_audit_log
from app.services.retrieval import config_profile_to_rule, rank_knowledge_items, scope_matches
from app.utils import api_response, generate_id


router = APIRouter(prefix='/api/v1', tags=['retrieval'])


def _build_context_pack(database: Session, payload: RetrievalQueryRequest, persist: bool) -> tuple[dict, dict, str]:
    request_id = generate_id('ret')
    if persist:
        database.add(
            RetrievalRequest(
                request_id=request_id,
                session_id=payload.session_id,
                query_text=payload.query,
                query_type=payload.query_type,
                repo_id=payload.repo_id,
                branch_name=payload.branch_name,
                file_paths=payload.file_paths,
                token_budget=payload.token_budget,
            )
        )

    matching_profiles = [
        profile
        for profile in database.scalars(select(ConfigProfile).where(ConfigProfile.status == 'active')).all()
        if scope_matches(profile.scope_type, profile.scope_id, payload.repo_id, payload.file_paths)
    ]
    rules_from_profiles = []
    for profile in matching_profiles:
        rules_from_profiles.extend(config_profile_to_rule(profile))

    candidate_items = [
        item
        for item in database.scalars(select(KnowledgeItem).where(KnowledgeItem.status == 'active')).all()
        if scope_matches(item.scope_type, item.scope_id, payload.repo_id, payload.file_paths)
    ]

    ranked_items, vector_backend_name = rank_knowledge_items(candidate_items, payload.query, payload.repo_id, payload.file_paths)
    selected_items = ranked_items[:8]

    if persist:
        for rank, item in enumerate(selected_items, start=1):
            database.add(
                RetrievalResult(
                    request_id=request_id,
                    knowledge_id=item['knowledge_id'],
                    recall_channel='hybrid',
                    recall_score=item['lexical_score'],
                    rerank_score=item['score'],
                    selected=True,
                    selected_rank=rank,
                )
            )

    rules = rules_from_profiles + [item for item in selected_items if item['knowledge_type'] == 'rule']
    cases = [item for item in selected_items if item['knowledge_type'] == 'case']
    procedures = [item for item in selected_items if item['knowledge_type'] == 'procedure']
    summary_lines = [entry['title'] for entry in (rules[:2] + cases[:1] + procedures[:1])]

    context_pack = {
        'context_summary': '；'.join(summary_lines) if summary_lines else '未命中特定知识，建议优先查看当前仓库和路径规则。',
        'rules': rules,
        'cases': cases,
        'procedures': procedures,
        'sources': [
            {'knowledge_id': item['knowledge_id'], 'source_type': item['source_type']}
            for item in (rules + cases + procedures)
        ],
    }
    debug_payload = {
        'request_id': request_id,
        'route_decision': {
            'query_type': payload.query_type,
            'repo_id': payload.repo_id,
            'matched_paths': payload.file_paths,
            'strategy': 'hybrid-retrieval-with-config-scope-and-vector-layer',
            'vector_backend': vector_backend_name,
        },
        'matching_profiles': [
            {
                'profile_id': profile.profile_id,
                'scope_type': profile.scope_type,
                'scope_id': profile.scope_id,
                'profile_type': profile.profile_type,
                'version': profile.version,
            }
            for profile in matching_profiles
        ],
        'candidate_scores': selected_items,
    }
    return context_pack, debug_payload, request_id


@router.post('/retrieval/query')
def retrieve_context_pack(payload: RetrievalQueryRequest, database: Session = Depends(get_db)):
    context_pack, debug_payload, request_id = _build_context_pack(database, payload, persist=True)
    append_audit_log(
        database,
        actor_id='system',
        action='retrieval.query',
        resource_type='retrieval',
        resource_id=request_id,
        scope_type='repo',
        scope_id=payload.repo_id,
        detail={
            'query_type': payload.query_type,
            'candidate_count': len(debug_payload['candidate_scores']),
            'vector_backend': debug_payload['route_decision']['vector_backend'],
        },
    )
    database.commit()
    return api_response(context_pack, request_id=request_id)


@router.post('/retrieval/debug')
def debug_retrieval(payload: RetrievalQueryRequest, database: Session = Depends(get_db)):
    context_pack, debug_payload, _ = _build_context_pack(database, payload, persist=False)
    return api_response({'context_pack': context_pack, 'debug': debug_payload})


@router.get('/retrieval/logs')
def list_retrieval_logs(database: Session = Depends(get_db)):
    logs = database.scalars(select(RetrievalRequest).order_by(RetrievalRequest.requested_at.desc())).all()
    counts = {
        request_id: count
        for request_id, count in database.execute(
            select(RetrievalResult.request_id, func.count(RetrievalResult.id)).group_by(RetrievalResult.request_id)
        ).all()
    }
    return api_response(
        [
            {
                'request_id': log.request_id,
                'session_id': log.session_id,
                'query_text': log.query_text,
                'query_type': log.query_type,
                'repo_id': log.repo_id,
                'result_count': counts.get(log.request_id, 0),
                'requested_at': log.requested_at.isoformat(),
            }
            for log in logs
        ]
    )
