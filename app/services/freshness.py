from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ConversationSession, KnowledgeItem, SessionEvent, utc_now
from app.services.audit import append_audit_log
from app.utils import extract_keywords, keyword_overlap_score, to_text


INVALIDATION_TRIGGER_KEYWORDS = {
    '迁移',
    '下线',
    '废弃',
    '替换',
    '移除',
    '重构',
    '升级',
    '切换',
    'deprecated',
    'replace',
    'replaced',
    'remove',
    'removed',
    'migrate',
    'migration',
    'sunset',
}
HARD_DEPRECATION_KEYWORDS = {
    '下线',
    '废弃',
    '替换',
    '移除',
    'deprecated',
    'replace',
    'replaced',
    'remove',
    'removed',
    'sunset',
}


@dataclass
class FreshnessUpdate:
    knowledge_id: str
    action: str
    freshness_score: float
    status: str
    matched_signals: list[str]
    overlap_score: float


def _scope_matches_knowledge(knowledge: KnowledgeItem, session: ConversationSession, file_paths: list[str]) -> bool:
    if knowledge.scope_type == 'global':
        return True
    if knowledge.scope_type == 'repo':
        return knowledge.scope_id == session.repo_id
    if knowledge.scope_type == 'path':
        return any(path.startswith(knowledge.scope_id) for path in file_paths)
    return False


def _knowledge_text(knowledge: KnowledgeItem) -> str:
    return ' '.join(
        [
            knowledge.title,
            to_text(knowledge.content.get('background')),
            to_text(knowledge.content.get('conclusion')),
            to_text(knowledge.content.get('summary')),
            to_text(knowledge.content.get('tags')),
        ]
    )


def _event_has_invalidation_trigger(event: SessionEvent) -> bool:
    lowered_summary = (event.summary or '').lower()
    return any(keyword in lowered_summary for keyword in INVALIDATION_TRIGGER_KEYWORDS)


def _matched_invalidation_signals(knowledge: KnowledgeItem, event: SessionEvent) -> list[str]:
    summary = (event.summary or '').lower()
    signals = knowledge.content.get('invalidation_signals') or []
    return [signal for signal in signals if isinstance(signal, str) and signal.lower() in summary]


def _infer_event_keywords(event: SessionEvent) -> list[str]:
    return extract_keywords(event.summary or '')


def apply_knowledge_freshness_updates(
    database: Session,
    *,
    session: ConversationSession,
    event: SessionEvent,
    actor_id: str,
) -> list[FreshnessUpdate]:
    if not _event_has_invalidation_trigger(event):
        return []

    candidate_items = database.scalars(
        select(KnowledgeItem).where(KnowledgeItem.status == 'active').order_by(KnowledgeItem.updated_at.desc())
    ).all()
    event_keywords = _infer_event_keywords(event)
    updates: list[FreshnessUpdate] = []

    for knowledge in candidate_items:
        if not _scope_matches_knowledge(knowledge, session, event.file_paths):
            continue

        matched_signals = _matched_invalidation_signals(knowledge, event)
        overlap_score = keyword_overlap_score(event.summary or '', _knowledge_text(knowledge))
        keyword_overlap_hits = sum(1 for keyword in event_keywords if keyword in _knowledge_text(knowledge).lower())

        if not matched_signals and overlap_score < 0.28 and keyword_overlap_hits < 2:
            continue

        previous_status = knowledge.status
        previous_freshness = float(knowledge.freshness_score)
        lowered_summary = (event.summary or '').lower()
        hard_deprecation = bool(matched_signals) or any(
            keyword in lowered_summary for keyword in HARD_DEPRECATION_KEYWORDS
        )

        if hard_deprecation:
            knowledge.status = 'deprecated'
            knowledge.effective_to = utc_now()
            knowledge.freshness_score = 0.1
            action = 'deprecated'
        else:
            knowledge.freshness_score = round(max(0.1, previous_freshness - 0.35), 4)
            action = 'freshness_decay'

        append_audit_log(
            database,
            actor_id=actor_id,
            action='knowledge.auto_invalidate',
            resource_type='knowledge',
            resource_id=knowledge.knowledge_id,
            scope_type=knowledge.scope_type,
            scope_id=knowledge.scope_id,
            detail={
                'event_id': event.event_id,
                'event_type': event.event_type,
                'trigger_summary': event.summary,
                'matched_signals': matched_signals,
                'overlap_score': round(overlap_score, 4),
                'keyword_overlap_hits': keyword_overlap_hits,
                'previous_status': previous_status,
                'previous_freshness': previous_freshness,
                'new_status': knowledge.status,
                'new_freshness': float(knowledge.freshness_score),
                'action': action,
            },
        )
        updates.append(
            FreshnessUpdate(
                knowledge_id=knowledge.knowledge_id,
                action=action,
                freshness_score=float(knowledge.freshness_score),
                status=knowledge.status,
                matched_signals=matched_signals,
                overlap_score=round(overlap_score, 4),
            )
        )

    return updates
