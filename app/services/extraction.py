from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass

from app.models import ConversationSession, KnowledgeSignal, SessionEvent
from app.services.llm_validation import LlmGatewayError, request_chat_completion
from app.settings import AppSettings, load_settings
from app.utils import extract_keywords, keyword_overlap_score


MEMORY_MAPPING = {
    'rule': 'semantic',
    'case': 'episodic',
    'procedure': 'procedural',
}

PROMPT_VERSION = 'v2'
ALLOWED_TYPES = {'rule', 'case', 'procedure'}


@dataclass
class ExtractionDraft:
    title: str
    knowledge_type: str
    memory_type: str
    content: dict
    quality_score: float
    confidence_score: float
    freshness_score: float
    created_by: str
    model_name: str
    prompt_version: str


def _clamp_score(value: float | int | str | None, default: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return round(max(0.1, min(numeric, 1.0)), 4)


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r'[\u4e00-\u9fff]', text or ''))


def build_joined_summary(signal: KnowledgeSignal, events: list[SessionEvent]) -> str:
    return '\n'.join(event.summary for event in reversed(events)) or signal.source_refs.get('summary', '')


def _default_title(signal_type: str, title_body: str) -> str:
    title_prefix = {'rule': '规则', 'case': '案例', 'procedure': '流程'}.get(signal_type, '知识')
    return f'{title_prefix}：{title_body[:80] or "自动提取内容"}'


def _normalize_tags(raw_tags: list | None, *, repo_id: str | None, knowledge_type: str, joined_summary: str) -> list[str]:
    tags: list[str] = []
    for entry in raw_tags or []:
        if isinstance(entry, str) and entry.strip():
            tags.append(entry.strip()[:64])
    if repo_id:
        tags.append(repo_id)
    tags.append(knowledge_type)
    tags.extend(extract_keywords(joined_summary)[:6])
    return list(dict.fromkeys(tags))[:10]


def _heuristic_scope(session: ConversationSession | None, file_paths: list[str]) -> tuple[str, str]:
    if file_paths:
        first_path = file_paths[0]
        common_path = first_path.rsplit('/', 1)[0] if '/' in first_path else first_path
        if common_path and common_path != first_path:
            return 'path', common_path
    if session:
        return 'repo', session.repo_id
    return 'global', 'global'


def build_heuristic_draft(
    signal: KnowledgeSignal,
    session: ConversationSession | None,
    events: list[SessionEvent],
) -> ExtractionDraft:
    joined_summary = build_joined_summary(signal, events)
    file_paths = signal.source_refs.get('file_paths') or []
    title_body = signal.source_refs.get('summary') or (joined_summary.splitlines()[0] if joined_summary else '')
    scope_type, scope_id = _heuristic_scope(session, file_paths)
    knowledge_type = signal.signal_type if signal.signal_type in ALLOWED_TYPES else 'rule'
    return ExtractionDraft(
        title=_default_title(knowledge_type, title_body),
        knowledge_type=knowledge_type,
        memory_type=MEMORY_MAPPING.get(knowledge_type, 'semantic'),
        content={
            'background': joined_summary[:500],
            'conclusion': signal.source_refs.get('summary', ''),
            'summary': joined_summary[:1200],
            'tags': _normalize_tags([], repo_id=session.repo_id if session else None, knowledge_type=knowledge_type, joined_summary=joined_summary),
            'scope_type': scope_type,
            'scope_id': scope_id,
            'source_session_id': signal.session_id,
            'file_paths': file_paths,
            'applicability': {'repo_id': session.repo_id if session else None, 'file_paths': file_paths},
            'invalidation_signals': [],
        },
        quality_score=_clamp_score(signal.confidence, 0.75),
        confidence_score=_clamp_score(signal.confidence, 0.75),
        freshness_score=1.0,
        created_by='heuristic-extractor',
        model_name='heuristic-extractor',
        prompt_version='v1',
    )


def _extract_json_block(text: str) -> dict:
    normalized = (text or '').strip()
    if normalized.startswith('```'):
        fence_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', normalized, flags=re.S)
        if fence_match:
            normalized = fence_match.group(1)
    try:
        return json.loads(normalized)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', normalized, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def _build_llm_messages(signal: KnowledgeSignal, session: ConversationSession | None, events: list[SessionEvent]) -> list[dict]:
    joined_summary = build_joined_summary(signal, events)
    file_paths = signal.source_refs.get('file_paths') or []
    output_language = 'zh-CN' if _contains_cjk(joined_summary) else 'same-as-input'
    instructions = {
        'task': 'Extract one reusable AI coding knowledge item from the provided session events.',
        'output_language': output_language,
        'output_format': {
            'title': 'string',
            'knowledge_type': 'rule|case|procedure',
            'memory_type': 'semantic|episodic|procedural',
            'background': 'string',
            'conclusion': 'string',
            'summary': 'string',
            'tags': ['string'],
            'scope_type': 'global|repo|path',
            'scope_id': 'string',
            'applicability': {'repo_id': 'string|null', 'file_paths': ['string']},
            'invalidation_signals': ['string'],
            'confidence_score': '0-1 float',
        },
        'rules': [
            'Return strict JSON only.',
            'Keep the output grounded in the supplied events.',
            'Prefer repo scope unless the knowledge is clearly limited to a path.',
            'If the source summaries are Chinese, output Chinese.',
        ],
    }
    input_payload = {
        'signal_type': signal.signal_type,
        'signal_confidence': float(signal.confidence),
        'repo_id': session.repo_id if session else None,
        'branch_name': session.branch_name if session else None,
        'task_id': session.task_id if session else None,
        'file_paths': file_paths,
        'joined_summary': joined_summary,
        'recent_events': [
            {
                'event_type': event.event_type,
                'summary': event.summary,
                'file_paths': event.file_paths,
            }
            for event in events
        ],
    }
    return [
        {
            'role': 'system',
            'content': 'You extract structured engineering knowledge. Output JSON only and do not include markdown fences.',
        },
        {
            'role': 'user',
            'content': json.dumps({'instructions': instructions, 'input': input_payload}, ensure_ascii=False),
        },
    ]


def _normalize_llm_draft(
    payload: dict,
    signal: KnowledgeSignal,
    session: ConversationSession | None,
    events: list[SessionEvent],
    settings: AppSettings,
) -> ExtractionDraft:
    joined_summary = build_joined_summary(signal, events)
    knowledge_type = payload.get('knowledge_type')
    if knowledge_type not in ALLOWED_TYPES:
        knowledge_type = signal.signal_type if signal.signal_type in ALLOWED_TYPES else 'rule'

    memory_type = payload.get('memory_type')
    if memory_type not in {'semantic', 'episodic', 'procedural'}:
        memory_type = MEMORY_MAPPING.get(knowledge_type, 'semantic')

    file_paths = signal.source_refs.get('file_paths') or []
    scope_type = payload.get('scope_type') if payload.get('scope_type') in {'global', 'repo', 'path'} else None
    scope_id = str(payload.get('scope_id') or '').strip() or None
    if not scope_type or not scope_id:
        scope_type, scope_id = _heuristic_scope(session, file_paths)

    title = str(payload.get('title') or '').strip()
    if not title:
        title = _default_title(knowledge_type, signal.source_refs.get('summary') or joined_summary[:80])

    confidence_score = _clamp_score(payload.get('confidence_score'), float(signal.confidence))
    quality_score = round(max(confidence_score, float(signal.confidence)), 4)
    content = {
        'background': str(payload.get('background') or joined_summary[:500]).strip(),
        'conclusion': str(payload.get('conclusion') or signal.source_refs.get('summary', '')).strip(),
        'summary': str(payload.get('summary') or joined_summary[:1200]).strip(),
        'tags': _normalize_tags(payload.get('tags'), repo_id=session.repo_id if session else None, knowledge_type=knowledge_type, joined_summary=joined_summary),
        'scope_type': scope_type,
        'scope_id': scope_id,
        'source_session_id': signal.session_id,
        'file_paths': file_paths,
        'applicability': payload.get('applicability') or {'repo_id': session.repo_id if session else None, 'file_paths': file_paths},
        'invalidation_signals': payload.get('invalidation_signals') or [],
    }
    return ExtractionDraft(
        title=title[:256],
        knowledge_type=knowledge_type,
        memory_type=memory_type,
        content=content,
        quality_score=quality_score,
        confidence_score=confidence_score,
        freshness_score=1.0,
        created_by='llm-extractor',
        model_name=settings.llm_model or 'llm-extractor',
        prompt_version=PROMPT_VERSION,
    )


def extract_knowledge_draft(
    signal: KnowledgeSignal,
    session: ConversationSession | None,
    events: list[SessionEvent],
    *,
    settings: AppSettings | None = None,
    urlopen=None,
) -> ExtractionDraft:
    app_settings = settings or load_settings()
    heuristic_draft = build_heuristic_draft(signal, session, events)
    if not app_settings.llm_configured:
        return heuristic_draft

    try:
        llm_urlopen = urlopen if urlopen is not None else urllib.request.urlopen
        completion = request_chat_completion(
            app_settings,
            messages=_build_llm_messages(signal, session, events),
            max_tokens=700,
            temperature=0,
            urlopen=llm_urlopen,
        )
        payload = _extract_json_block(completion.response_text)
        llm_draft = _normalize_llm_draft(payload, signal, session, events, app_settings)
        if _contains_cjk(build_joined_summary(signal, events)) and not _contains_cjk(
            f"{llm_draft.title}\n{llm_draft.content.get('background', '')}\n{llm_draft.content.get('summary', '')}"
        ):
            return heuristic_draft
        if keyword_overlap_score(llm_draft.title, build_joined_summary(signal, events)) < 0.1 and signal.signal_type == 'rule':
            return heuristic_draft
        return llm_draft
    except (LlmGatewayError, json.JSONDecodeError, ValueError, TypeError):
        return heuristic_draft
