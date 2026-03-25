from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import ContextPackFeedback, KnowledgeFeedback, KnowledgeItem, RetrievalRequest
from app.request_context import get_request_context
from app.schemas import ContextPackFeedbackRequest, FeedbackRequest
from app.services.audit import append_audit_log
from app.utils import api_response


router = APIRouter(prefix="/api/v1", tags=["feedback"])


@router.post("/feedback/knowledge")
def submit_knowledge_feedback(payload: FeedbackRequest, database: Session = Depends(get_db)):
    request_context = get_request_context()
    knowledge = database.scalar(select(KnowledgeItem).where(KnowledgeItem.knowledge_id == payload.knowledge_id))
    if not knowledge:
        raise HTTPException(status_code=404, detail="knowledge not found")

    database.add(
        KnowledgeFeedback(
            knowledge_id=payload.knowledge_id,
            request_id=payload.request_id,
            feedback_type=payload.feedback_type,
            feedback_score=payload.feedback_score,
            feedback_text=payload.feedback_text,
            created_by=payload.created_by,
        )
    )

    normalized_score = max(1, min(payload.feedback_score, 5)) / 5
    knowledge.quality_score = round((float(knowledge.quality_score) * 0.7) + (normalized_score * 0.3), 4)
    if payload.feedback_type in {"wrong", "stale"}:
        knowledge.freshness_score = round(max(0.1, float(knowledge.freshness_score) - 0.2), 4)

    append_audit_log(
        database,
        actor_id=request_context.user_id or payload.created_by,
        action="feedback.knowledge",
        resource_type="knowledge",
        resource_id=payload.knowledge_id,
        scope_type=knowledge.scope_type,
        scope_id=knowledge.scope_id,
        detail={"feedback_type": payload.feedback_type, "feedback_score": payload.feedback_score},
    )
    database.commit()
    return api_response(
        {
            "knowledge_id": knowledge.knowledge_id,
            "quality_score": float(knowledge.quality_score),
            "freshness_score": float(knowledge.freshness_score),
        }
    )


@router.post("/feedback/context-pack")
def submit_context_pack_feedback(payload: ContextPackFeedbackRequest, database: Session = Depends(get_db)):
    request_context = get_request_context()
    request = database.scalar(select(RetrievalRequest).where(RetrievalRequest.request_id == payload.request_id))
    if not request:
        raise HTTPException(status_code=404, detail="retrieval request not found")

    database.add(
        ContextPackFeedback(
            request_id=payload.request_id,
            feedback_score=payload.feedback_score,
            relevance_score=payload.relevance_score,
            completeness_score=payload.completeness_score,
            feedback_text=payload.feedback_text,
            created_by=payload.created_by,
        )
    )
    append_audit_log(
        database,
        actor_id=request_context.user_id or payload.created_by,
        action="feedback.context_pack",
        resource_type="retrieval",
        resource_id=payload.request_id,
        scope_type="repo",
        scope_id=request.repo_id,
        detail={
            "feedback_score": payload.feedback_score,
            "relevance_score": payload.relevance_score,
            "completeness_score": payload.completeness_score,
        },
    )
    database.commit()
    return api_response({"request_id": payload.request_id, "status": "recorded"})
