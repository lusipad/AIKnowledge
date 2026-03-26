from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.request_context import get_request_context
from app.schemas import KnowledgeRelationCreateRequest
from app.security import require_min_role
from app.services.graph import KnowledgeGraphError, get_knowledge_graph, get_repo_knowledge_map, upsert_knowledge_relation
from app.utils import api_response


router = APIRouter(prefix='/api/v1', tags=['graph'])


@router.post('/graph/relations')
def create_graph_relation(
    payload: KnowledgeRelationCreateRequest,
    database: Session = Depends(get_db),
    _: str = Depends(require_min_role('reviewer')),
):
    try:
        relation = upsert_knowledge_relation(database, payload, get_request_context())
        database.commit()
        return api_response(relation)
    except KnowledgeGraphError as exc:
        database.rollback()
        detail = str(exc)
        status_code = 404 if detail.startswith('knowledge not found') else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get('/graph/knowledge/{knowledge_id}')
def get_graph_for_knowledge(
    knowledge_id: str,
    database: Session = Depends(get_db),
    _: str = Depends(require_min_role('viewer')),
):
    try:
        return api_response(get_knowledge_graph(database, knowledge_id, get_request_context()))
    except KnowledgeGraphError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get('/graph/repos/{repo_id}/knowledge-map')
def get_graph_for_repo(
    repo_id: str,
    database: Session = Depends(get_db),
    _: str = Depends(require_min_role('viewer')),
):
    return api_response(get_repo_knowledge_map(database, repo_id, get_request_context()))
