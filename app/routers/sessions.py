from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import ConversationSession
from app.schemas import SessionCreateRequest
from app.services.use_cases import create_session_data
from app.utils import api_response


router = APIRouter(prefix="/api/v1", tags=["sessions"])


@router.post("/sessions")
def create_session(payload: SessionCreateRequest, database: Session = Depends(get_db)):
    return api_response(create_session_data(payload, database))


@router.get("/sessions/{session_id}")
def get_session(session_id: str, database: Session = Depends(get_db)):
    session = database.scalar(select(ConversationSession).where(ConversationSession.session_id == session_id))
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    return api_response(
        {
            "session_id": session.session_id,
            "tenant_id": session.tenant_id,
            "team_id": session.team_id,
            "user_id": session.user_id,
            "repo_id": session.repo_id,
            "branch_name": session.branch_name,
            "task_id": session.task_id,
            "client_type": session.client_type,
            "status": session.status,
            "started_at": session.started_at.isoformat(),
            "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        }
    )
