from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import (
    KnowledgeItem,
    KnowledgeReview,
    utc_now,
)
from app.request_context import get_request_context
from app.security import require_min_role
from app.schemas import ExtractRequest, KnowledgeDeprecateRequest, KnowledgeUpdateRequest, ReviewRequest
from app.services.audit import append_audit_log
from app.services.isolation import apply_knowledge_scope
from app.services.use_cases import (
    AuthorizationError,
    InvalidOperationError,
    ResourceNotFoundError,
    create_extract_task_data,
    get_extract_task_data,
    get_knowledge_data,
    review_knowledge_data,
)
from app.services.vector_store import sync_knowledge_vector_index
from app.utils import api_response


router = APIRouter(prefix="/api/v1", tags=["knowledge"])


@router.post("/knowledge/extract")
def create_extract_task(
    payload: ExtractRequest,
    database: Session = Depends(get_db),
    _: str = Depends(require_min_role('writer')),
):
    try:
        return api_response(create_extract_task_data(payload, database))
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/knowledge/extract/{task_id}")
def get_extract_task(
    task_id: str,
    database: Session = Depends(get_db),
    _: str = Depends(require_min_role('viewer')),
):
    try:
        return api_response(get_extract_task_data(task_id, database, request_context=get_request_context()))
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/knowledge/review")
def review_knowledge(
    payload: ReviewRequest,
    database: Session = Depends(get_db),
    _: str = Depends(require_min_role('reviewer')),
):
    try:
        return api_response(review_knowledge_data(payload, database))
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except InvalidOperationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/knowledge")
def list_knowledge(
    scope_type: str | None = None,
    scope_id: str | None = None,
    knowledge_type: str | None = None,
    memory_type: str | None = None,
    status: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    database: Session = Depends(get_db),
    _: str = Depends(require_min_role('viewer')),
):
    statement = apply_knowledge_scope(select(KnowledgeItem).order_by(KnowledgeItem.updated_at.desc()))
    if scope_type:
        statement = statement.where(KnowledgeItem.scope_type == scope_type)
    if scope_id:
        statement = statement.where(KnowledgeItem.scope_id == scope_id)
    if knowledge_type:
        statement = statement.where(KnowledgeItem.knowledge_type == knowledge_type)
    if memory_type:
        statement = statement.where(KnowledgeItem.memory_type == memory_type)
    if status:
        statement = statement.where(KnowledgeItem.status == status)

    knowledge_items = database.scalars(statement).all()
    if keyword:
        lowered_keyword = keyword.lower()
        knowledge_items = [
            item
            for item in knowledge_items
            if lowered_keyword in item.title.lower() or lowered_keyword in str(item.content).lower()
        ]

    normalized_page = max(1, page)
    normalized_page_size = max(1, min(page_size, 100))
    start_index = (normalized_page - 1) * normalized_page_size
    paginated_items = knowledge_items[start_index : start_index + normalized_page_size]
    return api_response(
        {
            "items": [
                {
                    "knowledge_id": item.knowledge_id,
                    "title": item.title,
                    "knowledge_type": item.knowledge_type,
                    "memory_type": item.memory_type,
                    "scope_type": item.scope_type,
                    "scope_id": item.scope_id,
                    "status": item.status,
                    "quality_score": float(item.quality_score),
                    "updated_at": item.updated_at.isoformat(),
                }
                for item in paginated_items
            ],
            "page": normalized_page,
            "page_size": normalized_page_size,
            "total": len(knowledge_items),
        }
    )


@router.get("/knowledge/{knowledge_id}")
def get_knowledge(
    knowledge_id: str,
    database: Session = Depends(get_db),
    _: str = Depends(require_min_role('viewer')),
):
    try:
        return api_response(get_knowledge_data(knowledge_id, database))
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/knowledge/{knowledge_id}")
def update_knowledge(
    knowledge_id: str,
    payload: KnowledgeUpdateRequest,
    database: Session = Depends(get_db),
    _: str = Depends(require_min_role('admin')),
):
    request_context = get_request_context()
    knowledge = database.scalar(apply_knowledge_scope(select(KnowledgeItem).where(KnowledgeItem.knowledge_id == knowledge_id)))
    if not knowledge:
        raise HTTPException(status_code=404, detail="knowledge not found")

    updated = False
    if payload.title is not None:
        knowledge.title = payload.title
        updated = True
    if payload.content is not None:
        knowledge.content = payload.content
        updated = True
    if payload.status is not None:
        knowledge.status = payload.status
        updated = True
    if payload.effective_to is not None:
        knowledge.effective_to = payload.effective_to
        updated = True

    if updated:
        knowledge.version += 1
        sync_knowledge_vector_index(database, knowledge)
        append_audit_log(
            database,
            actor_id=request_context.user_id or "system",
            action="knowledge.update",
            resource_type="knowledge",
            resource_id=knowledge_id,
            scope_type=knowledge.scope_type,
            scope_id=knowledge.scope_id,
            detail={"status": knowledge.status, "version": knowledge.version},
        )
        database.commit()
    return api_response(
        {
            "knowledge_id": knowledge.knowledge_id,
            "status": knowledge.status,
            "version": knowledge.version,
        }
    )


@router.post("/knowledge/{knowledge_id}/deprecate")
def deprecate_knowledge(
    knowledge_id: str,
    payload: KnowledgeDeprecateRequest,
    database: Session = Depends(get_db),
    _: str = Depends(require_min_role('admin')),
):
    request_context = get_request_context()
    knowledge = database.scalar(apply_knowledge_scope(select(KnowledgeItem).where(KnowledgeItem.knowledge_id == knowledge_id)))
    if not knowledge:
        raise HTTPException(status_code=404, detail="knowledge not found")

    knowledge.status = "deprecated"
    knowledge.effective_to = utc_now()
    knowledge.version += 1
    sync_knowledge_vector_index(database, knowledge)
    append_audit_log(
        database,
        actor_id=request_context.user_id or payload.actor_id,
        action="knowledge.deprecate",
        resource_type="knowledge",
        resource_id=knowledge_id,
        scope_type=knowledge.scope_type,
        scope_id=knowledge.scope_id,
        detail={"reason": payload.reason, "version": knowledge.version},
    )
    database.commit()
    return api_response(
        {
            "knowledge_id": knowledge.knowledge_id,
            "status": knowledge.status,
            "effective_to": knowledge.effective_to.isoformat() if knowledge.effective_to else None,
        }
    )


@router.get("/knowledge/{knowledge_id}/reviews")
def list_knowledge_reviews(
    knowledge_id: str,
    database: Session = Depends(get_db),
    _: str = Depends(require_min_role('viewer')),
):
    knowledge = database.scalar(apply_knowledge_scope(select(KnowledgeItem).where(KnowledgeItem.knowledge_id == knowledge_id)))
    if not knowledge:
        raise HTTPException(status_code=404, detail="knowledge not found")

    reviews = database.scalars(
        select(KnowledgeReview).where(KnowledgeReview.knowledge_id == knowledge_id).order_by(KnowledgeReview.created_at.desc())
    ).all()
    return api_response(
        [
            {
                "review_id": review.review_id,
                "knowledge_id": review.knowledge_id,
                "reviewer_id": review.reviewer_id,
                "decision": review.decision,
                "comment": review.comment,
                "created_at": review.created_at.isoformat(),
            }
            for review in reviews
        ]
    )
