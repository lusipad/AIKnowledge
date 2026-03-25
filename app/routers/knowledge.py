from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import (
    ConversationSession,
    ExtractTask,
    KnowledgeCandidate,
    KnowledgeItem,
    KnowledgeReview,
    KnowledgeSignal,
    KnowledgeSourceRef,
    SessionEvent,
    utc_now,
)
from app.request_context import get_request_context
from app.schemas import ExtractRequest, KnowledgeDeprecateRequest, KnowledgeUpdateRequest, ReviewRequest
from app.services.audit import append_audit_log
from app.services.extraction import extract_knowledge_draft
from app.settings import load_settings
from app.utils import api_response, generate_id


router = APIRouter(prefix="/api/v1", tags=["knowledge"])


def _build_knowledge_from_signal(database: Session, signal: KnowledgeSignal) -> tuple[KnowledgeCandidate, ExtractTask, KnowledgeItem]:
    session = database.scalar(select(ConversationSession).where(ConversationSession.session_id == signal.session_id))
    events = database.scalars(
        select(SessionEvent)
        .where(SessionEvent.session_id == signal.session_id)
        .order_by(SessionEvent.event_time.desc())
        .limit(10)
    ).all()
    joined_summary = "\n".join(event.summary for event in reversed(events)) or signal.source_refs.get("summary", "")
    extraction = extract_knowledge_draft(signal, session, events, settings=load_settings())
    candidate = KnowledgeCandidate(
        candidate_id=generate_id("cand"),
        signal_id=signal.signal_id,
        candidate_type=extraction.knowledge_type,
        summary=joined_summary[:1500],
        scope_hint={
            "scope_type": extraction.content.get("scope_type", "repo"),
            "scope_id": extraction.content.get("scope_id", session.repo_id if session else "global"),
        },
        quality_score=extraction.quality_score,
        extract_prompt_version=extraction.prompt_version,
        status="reviewing",
    )
    database.add(candidate)
    database.flush()

    knowledge = KnowledgeItem(
        knowledge_id=generate_id("kn"),
        tenant_id=session.tenant_id if session else None,
        scope_type=extraction.content.get("scope_type", "repo" if session else "global"),
        scope_id=extraction.content.get("scope_id", session.repo_id if session else "global"),
        knowledge_type=extraction.knowledge_type,
        memory_type=extraction.memory_type,
        title=extraction.title,
        content=extraction.content,
        status="draft",
        quality_score=extraction.quality_score,
        confidence_score=extraction.confidence_score,
        freshness_score=extraction.freshness_score,
        created_by=extraction.created_by,
    )
    database.add(knowledge)
    database.flush()

    database.add(
        KnowledgeSourceRef(
            knowledge_id=knowledge.knowledge_id,
            ref_type="session",
            ref_target_id=signal.session_id,
            ref_path=(signal.source_refs.get("file_paths") or [None])[0],
            excerpt_summary=signal.source_refs.get("summary"),
        )
    )

    task = ExtractTask(
        task_id=generate_id("ext"),
        candidate_id=candidate.candidate_id,
        status="success",
        model_name=extraction.model_name,
        prompt_version=extraction.prompt_version,
        result_ref=knowledge.knowledge_id,
    )
    database.add(task)

    signal.status = "processed"
    return candidate, task, knowledge


def _find_existing_extract_result(database: Session, signal_id: str) -> tuple[KnowledgeCandidate, ExtractTask] | None:
    candidate = database.scalar(
        select(KnowledgeCandidate)
        .where(KnowledgeCandidate.signal_id == signal_id)
        .order_by(KnowledgeCandidate.created_at.desc())
    )
    if not candidate:
        return None

    task = database.scalar(
        select(ExtractTask)
        .where(ExtractTask.candidate_id == candidate.candidate_id)
        .order_by(ExtractTask.created_at.desc())
    )
    if not task:
        return None
    return candidate, task


@router.post("/knowledge/extract")
def create_extract_task(payload: ExtractRequest, database: Session = Depends(get_db)):
    request_context = get_request_context()
    signals = database.scalars(select(KnowledgeSignal).where(KnowledgeSignal.signal_id.in_(payload.signal_ids))).all()
    if not signals:
        raise HTTPException(status_code=404, detail="signals not found")

    created_items: list[dict] = []
    for signal in signals:
        existing = _find_existing_extract_result(database, signal.signal_id)
        if existing and not payload.force:
            candidate, task = existing
            created_items.append(
                {
                    "signal_id": signal.signal_id,
                    "candidate_id": candidate.candidate_id,
                    "task_id": task.task_id,
                    "knowledge_id": task.result_ref,
                    "status": task.status,
                    "deduplicated": True,
                }
            )
            continue

        candidate, task, knowledge = _build_knowledge_from_signal(database, signal)
        append_audit_log(
            database,
            actor_id=request_context.user_id or "system",
            action="knowledge.extract",
            resource_type="knowledge",
            resource_id=knowledge.knowledge_id,
            scope_type=knowledge.scope_type,
            scope_id=knowledge.scope_id,
            detail={"signal_id": signal.signal_id, "candidate_id": candidate.candidate_id, "task_id": task.task_id},
        )
        created_items.append(
            {
                "signal_id": signal.signal_id,
                "candidate_id": candidate.candidate_id,
                "task_id": task.task_id,
                "knowledge_id": knowledge.knowledge_id,
                "status": task.status,
                "deduplicated": False,
            }
        )

    database.commit()
    return api_response({"items": created_items})


@router.get("/knowledge/extract/{task_id}")
def get_extract_task(task_id: str, database: Session = Depends(get_db)):
    task = database.scalar(select(ExtractTask).where(ExtractTask.task_id == task_id))
    if not task:
        raise HTTPException(status_code=404, detail="extract task not found")
    return api_response(
        {
            "task_id": task.task_id,
            "candidate_id": task.candidate_id,
            "status": task.status,
            "model_name": task.model_name,
            "prompt_version": task.prompt_version,
            "result_ref": task.result_ref,
            "error_message": task.error_message,
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat(),
        }
    )


@router.post("/knowledge/review")
def review_knowledge(payload: ReviewRequest, database: Session = Depends(get_db)):
    knowledge = database.scalar(select(KnowledgeItem).where(KnowledgeItem.knowledge_id == payload.knowledge_id))
    if not knowledge:
        raise HTTPException(status_code=404, detail="knowledge not found")

    next_status = {"approve": "active", "reject": "deprecated", "revise": "draft"}.get(payload.decision)
    if not next_status:
        raise HTTPException(status_code=400, detail="unsupported decision")

    knowledge.status = next_status
    database.add(
        KnowledgeReview(
            knowledge_id=payload.knowledge_id,
            reviewer_id=payload.reviewer_id,
            decision=payload.decision,
            comment=payload.comment,
        )
    )
    append_audit_log(
        database,
        actor_id=payload.reviewer_id,
        action="knowledge.review",
        resource_type="knowledge",
        resource_id=payload.knowledge_id,
        scope_type=knowledge.scope_type,
        scope_id=knowledge.scope_id,
        detail={"decision": payload.decision, "comment": payload.comment},
    )
    database.commit()
    return api_response({"knowledge_id": knowledge.knowledge_id, "status": knowledge.status})


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
):
    statement = select(KnowledgeItem).order_by(KnowledgeItem.updated_at.desc())
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
def get_knowledge(knowledge_id: str, database: Session = Depends(get_db)):
    knowledge = database.scalar(select(KnowledgeItem).where(KnowledgeItem.knowledge_id == knowledge_id))
    if not knowledge:
        raise HTTPException(status_code=404, detail="knowledge not found")

    return api_response(
        {
            "knowledge_id": knowledge.knowledge_id,
            "title": knowledge.title,
            "knowledge_type": knowledge.knowledge_type,
            "memory_type": knowledge.memory_type,
            "scope_type": knowledge.scope_type,
            "scope_id": knowledge.scope_id,
            "content": knowledge.content,
            "status": knowledge.status,
            "quality_score": float(knowledge.quality_score),
            "confidence_score": float(knowledge.confidence_score),
            "freshness_score": float(knowledge.freshness_score),
            "version": knowledge.version,
            "effective_to": knowledge.effective_to.isoformat() if knowledge.effective_to else None,
            "sources": [
                {
                    "ref_type": source.ref_type,
                    "ref_target_id": source.ref_target_id,
                    "ref_path": source.ref_path,
                    "excerpt_summary": source.excerpt_summary,
                }
                for source in knowledge.sources
            ],
        }
    )


@router.patch("/knowledge/{knowledge_id}")
def update_knowledge(knowledge_id: str, payload: KnowledgeUpdateRequest, database: Session = Depends(get_db)):
    request_context = get_request_context()
    knowledge = database.scalar(select(KnowledgeItem).where(KnowledgeItem.knowledge_id == knowledge_id))
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
def deprecate_knowledge(knowledge_id: str, payload: KnowledgeDeprecateRequest, database: Session = Depends(get_db)):
    request_context = get_request_context()
    knowledge = database.scalar(select(KnowledgeItem).where(KnowledgeItem.knowledge_id == knowledge_id))
    if not knowledge:
        raise HTTPException(status_code=404, detail="knowledge not found")

    knowledge.status = "deprecated"
    knowledge.effective_to = utc_now()
    knowledge.version += 1
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
def list_knowledge_reviews(knowledge_id: str, database: Session = Depends(get_db)):
    knowledge = database.scalar(select(KnowledgeItem).where(KnowledgeItem.knowledge_id == knowledge_id))
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
