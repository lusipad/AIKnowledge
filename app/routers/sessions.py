from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import ConversationSession
from app.request_context import get_request_context
from app.schemas import SessionCreateRequest
from app.services.audit import append_audit_log
from app.utils import api_response, generate_id


router = APIRouter(prefix="/api/v1", tags=["sessions"])


@router.post("/sessions")
def create_session(payload: SessionCreateRequest, database: Session = Depends(get_db)):
    request_context = get_request_context()
    client_type = request_context.client_type or payload.client_type
    session = ConversationSession(
        session_id=generate_id("sess"),
        tenant_id=request_context.tenant_id,
        team_id=request_context.team_id,
        user_id=request_context.user_id,
        repo_id=payload.repo_id,
        branch_name=payload.branch_name,
        task_id=payload.task_id,
        client_type=client_type,
    )
    database.add(session)
    append_audit_log(
        database,
        actor_id=request_context.user_id or "system",
        action="session.create",
        resource_type="session",
        resource_id=session.session_id,
        scope_type="repo",
        scope_id=payload.repo_id,
        detail={
            "branch_name": payload.branch_name,
            "task_id": payload.task_id,
            "client_type": client_type,
        },
    )
    database.commit()
    database.refresh(session)
    return api_response(
        {
            "session_id": session.session_id,
            "tenant_id": session.tenant_id,
            "team_id": session.team_id,
            "user_id": session.user_id,
            "repo_id": session.repo_id,
            "branch_name": session.branch_name,
            "task_id": session.task_id,
            "started_at": session.started_at.isoformat(),
            "status": session.status,
            "client_type": session.client_type,
        }
    )


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
