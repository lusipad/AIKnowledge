from __future__ import annotations

from app.models import KnowledgeSignal, SessionEvent
from app.utils import generate_id


RULE_KEYWORDS = ["规则", "禁止", "必须", "约束", "规范", "不要", "must", "never"]
CASE_KEYWORDS = ["修复", "排查", "复盘", "回归", "passed", "success", "故障"]
PROCEDURE_KEYWORDS = ["步骤", "流程", "sop", "runbook", "checklist", "发布"]


def build_signal_from_event(event: SessionEvent) -> KnowledgeSignal | None:
    summary = (event.summary or "").lower()
    signal_type: str | None = None
    confidence = 0.0
    priority = 50

    if any(keyword in summary for keyword in RULE_KEYWORDS):
        signal_type = "rule"
        confidence = 0.82
        priority = 80
    elif any(keyword in summary for keyword in CASE_KEYWORDS) or event.event_type == "test_result":
        signal_type = "case"
        confidence = 0.74
        priority = 70
    elif any(keyword in summary for keyword in PROCEDURE_KEYWORDS):
        signal_type = "procedure"
        confidence = 0.7
        priority = 65

    if not signal_type:
        return None

    return KnowledgeSignal(
        signal_id=generate_id("sig"),
        session_id=event.session_id,
        signal_type=signal_type,
        confidence=confidence,
        priority=priority,
        status="pending",
        source_refs={
            "event_id": event.event_id,
            "event_type": event.event_type,
            "file_paths": event.file_paths,
            "summary": event.summary,
        },
    )

