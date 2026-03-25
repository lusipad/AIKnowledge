from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import RetrievalRequest, RetrievalResult
from app.schemas import RetrievalQueryRequest
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
