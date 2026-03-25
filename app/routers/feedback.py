from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.schemas import ContextPackFeedbackRequest, FeedbackRequest
from app.services.use_cases import (
    ResourceNotFoundError,
    submit_context_pack_feedback_data,
    submit_knowledge_feedback_data,
)
from app.utils import api_response


router = APIRouter(prefix="/api/v1", tags=["feedback"])


@router.post("/feedback/knowledge")
def submit_knowledge_feedback(payload: FeedbackRequest, database: Session = Depends(get_db)):
    try:
        return api_response(submit_knowledge_feedback_data(payload, database))
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/feedback/context-pack")
def submit_context_pack_feedback(payload: ContextPackFeedbackRequest, database: Session = Depends(get_db)):
    try:
        return api_response(submit_context_pack_feedback_data(payload, database))
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
