from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, Text, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ConversationSession(Base):
    __tablename__ = "conversation_session"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    team_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    repo_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    branch_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    client_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    events: Mapped[list[SessionEvent]] = relationship(back_populates="session")


class SessionEvent(Base):
    __tablename__ = "session_event"

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("conversation_session.session_id"), index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    event_subtype: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    content_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_paths: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    symbol_names: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    session: Mapped[ConversationSession] = relationship(back_populates="events")


class KnowledgeSignal(Base):
    __tablename__ = "knowledge_signal"

    signal_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("conversation_session.session_id"), index=True)
    signal_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    source_refs: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgeCandidate(Base):
    __tablename__ = "knowledge_candidate"

    candidate_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    signal_id: Mapped[str] = mapped_column(ForeignKey("knowledge_signal.signal_id"), index=True)
    candidate_type: Mapped[str] = mapped_column(String(32), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    scope_hint: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    quality_score: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0.6)
    extract_prompt_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgeItem(Base):
    __tablename__ = "knowledge_item"

    knowledge_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    scope_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    knowledge_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    memory_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", index=True)
    quality_score: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0.6)
    confidence_score: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0.6)
    freshness_score: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=1.0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    sources: Mapped[list[KnowledgeSourceRef]] = relationship(back_populates="knowledge")
    reviews: Mapped[list[KnowledgeReview]] = relationship(back_populates="knowledge")
    feedback_items: Mapped[list[KnowledgeFeedback]] = relationship(back_populates="knowledge")


class KnowledgeSourceRef(Base):
    __tablename__ = "knowledge_source_ref"

    ref_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    knowledge_id: Mapped[str] = mapped_column(ForeignKey("knowledge_item.knowledge_id"), index=True)
    ref_type: Mapped[str] = mapped_column(String(32), nullable=False)
    ref_target_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ref_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ref_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ref_pr: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ref_issue: Mapped[str | None] = mapped_column(String(64), nullable=True)
    excerpt_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    knowledge: Mapped[KnowledgeItem] = relationship(back_populates="sources")


class ExtractTask(Base):
    __tablename__ = "extract_task"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("knowledge_candidate.candidate_id"), index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    model_name: Mapped[str] = mapped_column(String(64), nullable=False, default="heuristic-extractor")
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    result_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class KnowledgeReview(Base):
    __tablename__ = "knowledge_review"

    review_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    knowledge_id: Mapped[str] = mapped_column(ForeignKey("knowledge_item.knowledge_id"), index=True)
    reviewer_id: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    knowledge: Mapped[KnowledgeItem] = relationship(back_populates="reviews")


class RetrievalRequest(Base):
    __tablename__ = "retrieval_request"

    request_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    query_type: Mapped[str] = mapped_column(String(32), nullable=False)
    repo_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    branch_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    file_paths: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    token_budget: Mapped[int] = mapped_column(Integer, nullable=False, default=4000)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RetrievalResult(Base):
    __tablename__ = "retrieval_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("retrieval_request.request_id"), index=True)
    knowledge_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    recall_channel: Mapped[str] = mapped_column(String(32), nullable=False)
    recall_score: Mapped[float] = mapped_column(Numeric(8, 6), nullable=False)
    rerank_score: Mapped[float] = mapped_column(Numeric(8, 6), nullable=False)
    selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    selected_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)


class KnowledgeFeedback(Base):
    __tablename__ = "knowledge_feedback"

    feedback_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    knowledge_id: Mapped[str] = mapped_column(ForeignKey("knowledge_item.knowledge_id"), index=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    feedback_type: Mapped[str] = mapped_column(String(32), nullable=False)
    feedback_score: Mapped[int] = mapped_column(Integer, nullable=False)
    feedback_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    knowledge: Mapped[KnowledgeItem] = relationship(back_populates="feedback_items")


class ContextPackFeedback(Base):
    __tablename__ = "context_pack_feedback"

    feedback_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    feedback_score: Mapped[int] = mapped_column(Integer, nullable=False)
    relevance_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completeness_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ConfigProfile(Base):
    __tablename__ = "config_profile"

    profile_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    scope_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    profile_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    content: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class ConfigProfileVersion(Base):
    __tablename__ = "config_profile_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuditLog(Base):
    __tablename__ = "audit_log"

    audit_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    resource_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scope_type: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    scope_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
