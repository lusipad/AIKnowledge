from __future__ import annotations

from app.models import ConfigProfile, KnowledgeItem
from app.services.vector_store import VectorDocument, create_vector_backend
from app.utils import keyword_overlap_score, similarity_score, to_text


vector_backend = create_vector_backend()


def scope_matches(scope_type: str, scope_id: str, repo_id: str | None, file_paths: list[str]) -> bool:
    if scope_type == 'global':
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
        scope_boost = 0.0
        if item.scope_type == 'repo' and item.scope_id == repo_id:
            scope_boost = 0.2
        if item.scope_type == 'path' and any(path.startswith(item.scope_id) for path in file_paths):
            scope_boost = 0.3

        content_text = build_knowledge_text(item)
        lexical_score = keyword_overlap_score(query, content_text)
        fuzzy_score = similarity_score(query, content_text[:300])
        vector_score = vector_matches.get(item.knowledge_id).score if item.knowledge_id in vector_matches else 0.0
        freshness_component = float(item.freshness_score or 0)
        quality_component = float(item.quality_score or 0)
        final_score = round(
            (lexical_score * 0.35)
            + (vector_score * 0.25)
            + (fuzzy_score * 0.15)
            + (scope_boost * 0.15)
            + (freshness_component * 0.05)
            + (quality_component * 0.05),
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
                'score': final_score,
            }
        )

    ranked_items.sort(key=lambda entry: entry['score'], reverse=True)
    return ranked_items, vector_backend.backend_name



def config_profile_to_rule(profile: ConfigProfile) -> list[dict]:
    instructions = profile.content.get('instructions', []) if profile.content else []
    return [
        {
            'knowledge_id': f'config:{profile.profile_id}:{index}',
            'title': instruction,
            'content': instruction,
            'score': 0.98 if profile.scope_type == 'path' else 0.95,
            'lexical_score': 1.0,
            'vector_score': 1.0,
            'fuzzy_score': 1.0,
            'scope_boost': 1.0,
            'source_type': 'config_profile',
            'scope_type': profile.scope_type,
            'scope_id': profile.scope_id,
        }
        for index, instruction in enumerate(instructions, start=1)
    ]
