from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ResourceAclInput(BaseModel):
    owners: list[str] = Field(default_factory=list)
    editors: list[str] = Field(default_factory=list)
    reviewers: list[str] = Field(default_factory=list)
    viewers: list[str] = Field(default_factory=list)


class SessionCreateRequest(BaseModel):
    repo_id: str
    branch_name: str | None = None
    task_id: str | None = None
    client_type: str = "ide"


class SessionEventInput(BaseModel):
    event_type: str
    event_subtype: str | None = None
    summary: str
    content_ref: str | None = None
    tool_name: str | None = None
    file_paths: list[str] = Field(default_factory=list)
    symbol_names: list[str] = Field(default_factory=list)
    timestamp: datetime | None = None


class ContextEventsRequest(BaseModel):
    session_id: str
    events: list[SessionEventInput]


class RetrievalQueryRequest(BaseModel):
    session_id: str
    query: str
    query_type: str = "general"
    repo_id: str | None = None
    branch_name: str | None = None
    file_paths: list[str] = Field(default_factory=list)
    task_context: dict[str, Any] = Field(default_factory=dict)
    token_budget: int = 4000


class ExtractRequest(BaseModel):
    signal_ids: list[str]
    force: bool = False


class ReviewRequest(BaseModel):
    knowledge_id: str
    decision: str
    comment: str | None = None
    reviewer_id: str = "reviewer"


class KnowledgeUpdateRequest(BaseModel):
    title: str | None = None
    content: dict[str, Any] | None = None
    acl: ResourceAclInput | None = None
    status: str | None = None
    effective_to: datetime | None = None


class KnowledgeDeprecateRequest(BaseModel):
    actor_id: str = "system"
    reason: str | None = None


class FeedbackRequest(BaseModel):
    knowledge_id: str
    request_id: str | None = None
    feedback_type: str
    feedback_score: int
    feedback_text: str | None = None
    created_by: str = "user"


class ContextPackFeedbackRequest(BaseModel):
    request_id: str
    feedback_score: int
    relevance_score: int | None = None
    completeness_score: int | None = None
    feedback_text: str | None = None
    created_by: str = "user"


class ConfigProfileUpsertRequest(BaseModel):
    scope_type: str
    scope_id: str
    profile_type: str
    content: dict[str, Any] = Field(default_factory=dict)
    ownership_mode: str | None = None
    acl: ResourceAclInput | None = None
    version: int = 1
    status: str = "active"


class ConfigRollbackRequest(BaseModel):
    target_version: int | None = None
    actor_id: str = "system"


class LlmVerifyRequest(BaseModel):
    prompt: str = "Reply with ok only."
    max_tokens: int = 32


class EvaluationRunRequest(BaseModel):
    scenario_id: str = "order_risk_regression_zh"
    mode: str = "full"
    verify_llm: bool = True
    persist: bool = True
    repo_id: str | None = None
    branch_name: str | None = None
    task_id: str | None = None
    file_path: str | None = None
    profile_instruction: str | None = None
    event_prompt_summary: str | None = None
    event_result_summary: str | None = None
    query: str | None = None


class DirectoryUserUpsertRequest(BaseModel):
    tenant_id: str | None = None
    team_id: str | None = None
    external_ref: str | None = None
    email: str | None = None
    display_name: str | None = None
    active: bool = True
    attributes: dict[str, Any] = Field(default_factory=dict)


class DirectoryGroupUpsertRequest(BaseModel):
    tenant_id: str | None = None
    team_id: str | None = None
    external_ref: str | None = None
    display_name: str
    scope_type: str = 'team'
    scope_id: str | None = None
    mapped_role: str | None = None
    active: bool = True
    member_user_ids: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


class DirectorySyncRequest(BaseModel):
    users: dict[str, DirectoryUserUpsertRequest] = Field(default_factory=dict)
    groups: dict[str, DirectoryGroupUpsertRequest] = Field(default_factory=dict)


class KnowledgeRelationCreateRequest(BaseModel):
    knowledge_id: str
    related_knowledge_id: str
    relation_type: str
    repo_id: str | None = None
    related_repo_id: str | None = None
    weight: float = 1.0
    detail: dict[str, Any] = Field(default_factory=dict)
