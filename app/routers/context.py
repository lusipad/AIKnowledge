from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import KnowledgeSignal
from app.schemas import ContextEventsRequest
from app.services.use_cases import ResourceNotFoundError, append_context_events_data
from app.utils import api_response


router = APIRouter(prefix="/api/v1", tags=["context"])


@router.post("/context/events")
def append_context_events(payload: ContextEventsRequest, database: Session = Depends(get_db)):
    try:
        return api_response(append_context_events_data(payload, database))
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
