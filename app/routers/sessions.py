from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import ConversationSession, KnowledgeSignal, SessionEvent
from app.schemas import SessionCreateRequest
from app.services.use_cases import create_session_data
from app.utils import api_response


router = APIRouter(prefix="/api/v1", tags=["sessions"])


@router.post("/sessions")
def create_session(payload: SessionCreateRequest, database: Session = Depends(get_db)):
    return api_response(create_session_data(payload, database))


@router.get("/sessions")
def list_sessions(
    repo_id: str | None = None,
    status: str | None = None,
    client_type: str | None = None,
    task_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
    database: Session = Depends(get_db),
):
    normalized_page = max(1, page)
    normalized_page_size = max(1, min(page_size, 100))

    filters = []
    if repo_id:
        filters.append(ConversationSession.repo_id == repo_id)
    if status:
        filters.append(ConversationSession.status == status)
    if client_type:
        filters.append(ConversationSession.client_type == client_type)
    if task_id:
        filters.append(ConversationSession.task_id == task_id)

    count_statement = select(func.count()).select_from(ConversationSession)
    if filters:
        count_statement = count_statement.where(*filters)
    total = database.scalar(count_statement) or 0

    statement = select(ConversationSession).order_by(ConversationSession.started_at.desc())
    if filters:
        statement = statement.where(*filters)
    statement = statement.offset((normalized_page - 1) * normalized_page_size).limit(normalized_page_size)

    sessions = database.scalars(statement).all()
    session_ids = [session.session_id for session in sessions]
    event_counts = {}
    signal_counts = {}
    if session_ids:
        event_counts = {
            current_session_id: count
            for current_session_id, count in database.execute(
                select(SessionEvent.session_id, func.count(SessionEvent.event_id))
                .where(SessionEvent.session_id.in_(session_ids))
                .group_by(SessionEvent.session_id)
            ).all()
        }
        signal_counts = {
            current_session_id: count
            for current_session_id, count in database.execute(
                select(KnowledgeSignal.session_id, func.count(KnowledgeSignal.signal_id))
                .where(KnowledgeSignal.session_id.in_(session_ids))
                .group_by(KnowledgeSignal.session_id)
            ).all()
        }

    return api_response(
        {
            "items": [
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
                    "event_count": event_counts.get(session.session_id, 0),
                    "signal_count": signal_counts.get(session.session_id, 0),
                }
                for session in sessions
            ],
            "page": normalized_page,
            "page_size": normalized_page_size,
            "total": total,
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
