from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import ContextPackFeedback, KnowledgeFeedback, RetrievalRequest, RetrievalResult
from app.schemas import RetrievalQueryRequest
from app.services.isolation import apply_retrieval_request_scope
from app.services.use_cases import (
    ResourceNotFoundError,
    build_context_pack_data,
    retrieve_context_pack_data,
)
from app.utils import api_response


router = APIRouter(prefix='/api/v1', tags=['retrieval'])

@router.post('/retrieval/query')
def retrieve_context_pack(payload: RetrievalQueryRequest, database: Session = Depends(get_db)):
    try:
        context_pack, request_id = retrieve_context_pack_data(payload, database)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return api_response(context_pack, request_id=request_id)


@router.post('/retrieval/debug')
def debug_retrieval(payload: RetrievalQueryRequest, database: Session = Depends(get_db)):
    context_pack, debug_payload, _ = build_context_pack_data(database, payload, persist=False)
    return api_response({'context_pack': context_pack, 'debug': debug_payload})


@router.get('/retrieval/logs')
def list_retrieval_logs(
    session_id: str | None = None,
    repo_id: str | None = None,
    query_type: str | None = None,
    limit: int | None = None,
    database: Session = Depends(get_db),
):
    statement = apply_retrieval_request_scope(select(RetrievalRequest).order_by(RetrievalRequest.requested_at.desc()))
    if session_id:
        statement = statement.where(RetrievalRequest.session_id == session_id)
    if repo_id:
        statement = statement.where(RetrievalRequest.repo_id == repo_id)
    if query_type:
        statement = statement.where(RetrievalRequest.query_type == query_type)
    if limit is not None:
        statement = statement.limit(max(1, min(limit, 500)))

    logs = database.scalars(statement).all()
    request_ids = [log.request_id for log in logs]
    counts = {
        request_id: count
        for request_id, count in database.execute(
            select(RetrievalResult.request_id, func.count(RetrievalResult.id)).group_by(RetrievalResult.request_id)
        ).all()
    }
    latest_feedback: dict[str, ContextPackFeedback] = {}
    knowledge_feedback_counts: dict[str, int] = {}
    if request_ids:
        feedback_rows = database.scalars(
            select(ContextPackFeedback)
            .where(ContextPackFeedback.request_id.in_(request_ids))
            .order_by(ContextPackFeedback.created_at.desc())
        ).all()
        for row in feedback_rows:
            latest_feedback.setdefault(row.request_id, row)
        knowledge_feedback_counts = {
            current_request_id: count
            for current_request_id, count in database.execute(
                select(KnowledgeFeedback.request_id, func.count(KnowledgeFeedback.feedback_id))
                .where(KnowledgeFeedback.request_id.in_(request_ids))
                .group_by(KnowledgeFeedback.request_id)
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
                'context_feedback': (
                    {
                        'feedback_score': latest_feedback[log.request_id].feedback_score,
                        'relevance_score': latest_feedback[log.request_id].relevance_score,
                        'completeness_score': latest_feedback[log.request_id].completeness_score,
                        'created_at': latest_feedback[log.request_id].created_at.isoformat(),
                    }
                    if log.request_id in latest_feedback
                    else None
                ),
                'knowledge_feedback_count': knowledge_feedback_counts.get(log.request_id, 0),
                'requested_at': log.requested_at.isoformat(),
            }
            for log in logs
        ]
    )


@router.get('/retrieval/logs/{request_id}')
def get_retrieval_log(request_id: str, database: Session = Depends(get_db)):
    log = database.scalar(apply_retrieval_request_scope(select(RetrievalRequest).where(RetrievalRequest.request_id == request_id)))
    if not log:
        raise HTTPException(status_code=404, detail='retrieval log not found')

    results = database.scalars(
        select(RetrievalResult)
        .where(RetrievalResult.request_id == request_id)
        .order_by(
            RetrievalResult.selected.desc(),
            RetrievalResult.selected_rank.asc().nulls_last(),
            RetrievalResult.rerank_score.desc(),
        )
    ).all()
    context_feedback = database.scalars(
        select(ContextPackFeedback)
        .where(ContextPackFeedback.request_id == request_id)
        .order_by(ContextPackFeedback.created_at.desc())
    ).all()
    knowledge_feedback = database.scalars(
        select(KnowledgeFeedback)
        .where(KnowledgeFeedback.request_id == request_id)
        .order_by(KnowledgeFeedback.created_at.desc())
    ).all()

    return api_response(
        {
            'request_id': log.request_id,
            'session_id': log.session_id,
            'query_text': log.query_text,
            'query_type': log.query_type,
            'repo_id': log.repo_id,
            'branch_name': log.branch_name,
            'file_paths': log.file_paths,
            'token_budget': log.token_budget,
            'requested_at': log.requested_at.isoformat(),
            'results': [
                {
                    'knowledge_id': result.knowledge_id,
                    'recall_channel': result.recall_channel,
                    'recall_score': float(result.recall_score),
                    'rerank_score': float(result.rerank_score),
                    'selected': result.selected,
                    'selected_rank': result.selected_rank,
                }
                for result in results
            ],
            'context_pack_feedback': [
                {
                    'feedback_id': feedback.feedback_id,
                    'feedback_score': feedback.feedback_score,
                    'relevance_score': feedback.relevance_score,
                    'completeness_score': feedback.completeness_score,
                    'feedback_text': feedback.feedback_text,
                    'created_by': feedback.created_by,
                    'created_at': feedback.created_at.isoformat(),
                }
                for feedback in context_feedback
            ],
            'knowledge_feedback': [
                {
                    'feedback_id': feedback.feedback_id,
                    'knowledge_id': feedback.knowledge_id,
                    'feedback_type': feedback.feedback_type,
                    'feedback_score': feedback.feedback_score,
                    'feedback_text': feedback.feedback_text,
                    'created_by': feedback.created_by,
                    'created_at': feedback.created_at.isoformat(),
                }
                for feedback in knowledge_feedback
            ],
        }
    )
