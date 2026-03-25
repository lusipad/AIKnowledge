from __future__ import annotations

import re

from app.models import ConfigProfile, KnowledgeItem
from app.services.vector_store import VectorDocument, create_vector_backend
from app.utils import extract_keywords, keyword_overlap_score, similarity_score, to_text


vector_backend = create_vector_backend()

CONFIG_RULE_LIMITS = {'path': 2, 'repo': 1, 'team': 1, 'tenant': 1, 'global': 1}
CONFIG_RULE_SCORE_FLOORS = {'path': 0.12, 'repo': 0.17, 'team': 0.14, 'tenant': 0.15, 'global': 0.2}


def scope_matches(scope_type: str, scope_id: str, repo_id: str | None, file_paths: list[str]) -> bool:
    if scope_type == 'global':
        return True
    if scope_type in {'tenant', 'team'}:
        return True
    if scope_type == 'repo':
        return repo_id == scope_id
    if scope_type == 'path':
        return any(path.startswith(scope_id) for path in file_paths)
    return False


def build_knowledge_text(item: KnowledgeItem) -> str:
    return ' '.join(
        [
            item.title,
            to_text(item.content.get('background')),
            to_text(item.content.get('conclusion')),
            to_text(item.content.get('summary')),
            to_text(item.content.get('tags')),
        ]
    )


def _build_config_rule_text(profile: ConfigProfile, instruction: str) -> str:
    return ' '.join([profile.profile_type or 'prompt', profile.scope_type, profile.scope_id, instruction])


def _scope_boost(scope_type: str, scope_id: str, repo_id: str | None, file_paths: list[str]) -> float:
    if scope_type == 'path' and any(path.startswith(scope_id) for path in file_paths):
        depth = len([segment for segment in scope_id.split('/') if segment])
        return min(0.38, 0.22 + (depth * 0.02))
    if scope_type == 'repo' and repo_id == scope_id:
        return 0.18
    if scope_type == 'team':
        return 0.16
    if scope_type == 'tenant':
        return 0.12
    if scope_type == 'global':
        return 0.08
    return 0.0


def _specificity_score(text: str) -> float:
    keywords = extract_keywords(text)
    if not keywords:
        return 0.0
    return min(1.0, len(keywords) / 10)


def _entry_priority(entry: dict) -> tuple[float, int]:
    knowledge_bias = 0.06 if entry.get('source_type') == 'knowledge_item' else 0.0
    return (
        float(entry.get('score', 0.0)) + knowledge_bias,
        1 if entry.get('source_type') == 'knowledge_item' else 0,
    )


def _normalized_entry_text(entry: dict) -> str:
    raw_text = f"{entry.get('title', '')} {entry.get('content', '')}".lower()
    return re.sub(r'\s+', '', raw_text)


def dedupe_ranked_entries(entries: list[dict], *, similarity_threshold: float = 0.92) -> list[dict]:
    deduplicated: list[dict] = []
    seen_texts: list[str] = []
    for entry in sorted(entries, key=_entry_priority, reverse=True):
        normalized_text = _normalized_entry_text(entry)
        if not normalized_text:
            deduplicated.append(entry)
            continue
        if any(
            normalized_text == existing
            or similarity_score(normalized_text[:240], existing[:240]) >= similarity_threshold
            for existing in seen_texts
        ):
            continue
        seen_texts.append(normalized_text)
        deduplicated.append(entry)
    return deduplicated


def order_context_sources(rules: list[dict], cases: list[dict], procedures: list[dict]) -> list[dict]:
    return sorted(rules + cases + procedures, key=_entry_priority, reverse=True)


def build_context_summary(ordered_sources: list[dict]) -> str:
    summary_lines: list[str] = []
    summary_candidates = [
        entry
        for entry in ordered_sources
        if float(entry.get('score', 0.0)) >= 0.12 or not summary_lines
    ]

    for preferred_source_type in ('knowledge_item', 'config_profile'):
        for entry in summary_candidates:
            if len(summary_lines) >= 3 or entry.get('source_type') != preferred_source_type:
                continue
            line = (entry.get('content') or entry.get('title') or '').strip()
            if not line:
                continue
            if any(similarity_score(line[:180], existing[:180]) >= 0.9 for existing in summary_lines):
                continue
            summary_lines.append(line[:88])

    if not summary_lines and ordered_sources:
        fallback = (ordered_sources[0].get('content') or ordered_sources[0].get('title') or '').strip()
        if fallback:
            summary_lines.append(fallback[:88])

    return '；'.join(summary_lines) if summary_lines else '未命中特定知识，建议优先查看当前仓库和路径规则。'


def rank_knowledge_items(items: list[KnowledgeItem], query: str, repo_id: str | None, file_paths: list[str]) -> tuple[list[dict], str]:
    documents = [
        VectorDocument(
            document_id=item.knowledge_id,
            text=build_knowledge_text(item),
            metadata={
                'knowledge_type': item.knowledge_type,
                'scope_type': item.scope_type,
                'scope_id': item.scope_id,
                'title': item.title,
                'content': item.content.get('conclusion') or item.content.get('summary') or '',
            },
        )
        for item in items
    ]
    vector_matches = {match.document_id: match for match in vector_backend.score_documents(query, documents)}

    ranked_items: list[dict] = []
    for item in items:
        scope_boost = _scope_boost(item.scope_type, item.scope_id, repo_id, file_paths)
        content_text = build_knowledge_text(item)
        lexical_score = keyword_overlap_score(query, content_text)
        fuzzy_score = similarity_score(query, content_text[:300])
        vector_score = vector_matches.get(item.knowledge_id).score if item.knowledge_id in vector_matches else 0.0
        freshness_component = float(item.freshness_score or 0)
        quality_component = float(item.quality_score or 0)
        specificity_component = _specificity_score(content_text)
        final_score = round(
            (lexical_score * 0.33)
            + (vector_score * 0.25)
            + (fuzzy_score * 0.14)
            + (scope_boost * 0.15)
            + (freshness_component * 0.05)
            + (quality_component * 0.05)
            + (specificity_component * 0.03),
            6,
        )
        ranked_items.append(
            {
                'knowledge_id': item.knowledge_id,
                'title': item.title,
                'content': item.content.get('conclusion') or item.content.get('summary') or '',
                'knowledge_type': item.knowledge_type,
                'source_type': 'knowledge_item',
                'scope_type': item.scope_type,
                'scope_id': item.scope_id,
                'lexical_score': round(lexical_score, 6),
                'vector_score': round(vector_score, 6),
                'fuzzy_score': round(fuzzy_score, 6),
                'scope_boost': round(scope_boost, 6),
                'specificity_score': round(specificity_component, 6),
                'score': final_score,
            }
        )

    ranked_items.sort(key=_entry_priority, reverse=True)
    return ranked_items, vector_backend.backend_name


def rank_config_rules(
    profiles: list[ConfigProfile],
    query: str,
    repo_id: str | None,
    file_paths: list[str],
) -> tuple[list[dict], str]:
    documents: list[VectorDocument] = []
    rule_index: list[tuple[ConfigProfile, int, str]] = []
    for profile in profiles:
        instructions = profile.content.get('instructions', []) if profile.content else []
        for index, instruction in enumerate(instructions, start=1):
            rule_id = f'config:{profile.profile_id}:{index}'
            documents.append(
                VectorDocument(
                    document_id=rule_id,
                    text=_build_config_rule_text(profile, instruction),
                    metadata={'profile_id': profile.profile_id, 'scope_type': profile.scope_type, 'scope_id': profile.scope_id},
                )
            )
            rule_index.append((profile, index, instruction))

    vector_matches = {match.document_id: match for match in vector_backend.score_documents(query, documents)}
    ranked_rules: list[dict] = []
    for profile, index, instruction in rule_index:
        rule_id = f'config:{profile.profile_id}:{index}'
        scope_boost = _scope_boost(profile.scope_type, profile.scope_id, repo_id, file_paths)
        lexical_score = keyword_overlap_score(query, instruction)
        fuzzy_score = similarity_score(query, instruction[:240])
        vector_score = vector_matches.get(rule_id).score if rule_id in vector_matches else 0.0
        specificity_component = _specificity_score(instruction)
        final_score = round(
            (lexical_score * 0.32)
            + (vector_score * 0.22)
            + (fuzzy_score * 0.12)
            + (scope_boost * 0.22)
            + (specificity_component * 0.12),
            6,
        )
        ranked_rules.append(
            {
                'knowledge_id': rule_id,
                'title': instruction,
                'content': instruction,
                'knowledge_type': 'rule',
                'profile_id': profile.profile_id,
                'profile_type': profile.profile_type,
                'score': final_score,
                'lexical_score': round(lexical_score, 6),
                'vector_score': round(vector_score, 6),
                'fuzzy_score': round(fuzzy_score, 6),
                'scope_boost': round(scope_boost, 6),
                'specificity_score': round(specificity_component, 6),
                'source_type': 'config_profile',
                'scope_type': profile.scope_type,
                'scope_id': profile.scope_id,
            }
        )

    ranked_rules.sort(key=_entry_priority, reverse=True)
    return ranked_rules, vector_backend.backend_name


def select_config_rules(ranked_rules: list[dict]) -> list[dict]:
    selected: list[dict] = []
    selected_per_scope: dict[str, int] = {'path': 0, 'repo': 0, 'global': 0}

    for rule in dedupe_ranked_entries(ranked_rules):
        scope_type = rule.get('scope_type') or 'repo'
        if selected_per_scope.get(scope_type, 0) >= CONFIG_RULE_LIMITS.get(scope_type, 1):
            continue
        score_floor = CONFIG_RULE_SCORE_FLOORS.get(scope_type, 0.16)
        if float(rule.get('score', 0.0)) < score_floor:
            continue
        selected.append(rule)
        selected_per_scope[scope_type] = selected_per_scope.get(scope_type, 0) + 1
        if len(selected) >= sum(CONFIG_RULE_LIMITS.values()):
            break

    if not selected and ranked_rules:
        selected.append(dedupe_ranked_entries(ranked_rules)[0])

    return selected
