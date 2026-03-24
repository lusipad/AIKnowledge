from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import ConversationSession, KnowledgeSignal, SessionEvent
from app.schemas import ContextEventsRequest
from app.services.audit import append_audit_log
from app.services.signals import build_signal_from_event
from app.utils import api_response


router = APIRouter(prefix="/api/v1", tags=["context"])


@router.post("/context/events")
def append_context_events(payload: ContextEventsRequest, database: Session = Depends(get_db)):
    session = database.scalar(select(ConversationSession).where(ConversationSession.session_id == payload.session_id))
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    accepted_count = 0
    created_signal_ids: list[str] = []
    for item in payload.events:
        event = SessionEvent(
            session_id=payload.session_id,
            event_type=item.event_type,
            event_subtype=item.event_subtype,
            summary=item.summary,
            content_ref=item.content_ref,
            tool_name=item.tool_name,
            file_paths=item.file_paths,
            symbol_names=item.symbol_names,
            event_time=item.timestamp,
        )
        database.add(event)
        database.flush()
        accepted_count += 1

        signal = build_signal_from_event(event)
        if signal:
            database.add(signal)
            created_signal_ids.append(signal.signal_id)

    append_audit_log(
        database,
        actor_id="system",
        action="context.events.append",
        resource_type="session",
        resource_id=payload.session_id,
        scope_type="repo",
        scope_id=session.repo_id,
        detail={"accepted_count": accepted_count, "created_signal_ids": created_signal_ids},
    )
    database.commit()
    return api_response(
        {
            "session_id": payload.session_id,
            "accepted_count": accepted_count,
            "rejected_count": 0,
            "created_signal_ids": created_signal_ids,
        }
    )


@router.get("/signals")
def list_signals(status: str | None = None, database: Session = Depends(get_db)):
    statement = select(KnowledgeSignal).order_by(KnowledgeSignal.created_at.desc())
    if status:
        statement = statement.where(KnowledgeSignal.status == status)
    signals = database.scalars(statement).all()
    return api_response(
        [
            {
                "signal_id": signal.signal_id,
                "session_id": signal.session_id,
                "signal_type": signal.signal_type,
                "confidence": float(signal.confidence),
                "priority": signal.priority,
                "status": signal.status,
                "source_refs": signal.source_refs,
            }
            for signal in signals
        ]
    )
