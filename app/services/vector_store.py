from __future__ import annotations

import hashlib
import json
import math
import urllib.error
import urllib.request
from dataclasses import dataclass

from sqlalchemy import cast, delete, select
from sqlalchemy.orm import Session

from app.models import ConfigProfile, KnowledgeItem, VectorIndexEntry
from app.settings import AppSettings, load_settings
from app.utils import extract_keywords, to_text

try:
    from pgvector.sqlalchemy import Vector as PgVector
except ImportError:  # pragma: no cover - optional dependency in non-pgvector environments
    PgVector = None


@dataclass
class VectorDocument:
    document_id: str
    text: str
    metadata: dict


@dataclass
class VectorMatch:
    document_id: str
    score: float
    metadata: dict


class VectorBackend:
    backend_name = 'base'

    def score_documents(
        self,
        query: str,
        documents: list[VectorDocument],
        top_k: int | None = None,
        *,
        database: Session | None = None,
    ) -> list[VectorMatch]:
        raise NotImplementedError


class SimpleKeywordVectorBackend(VectorBackend):
    backend_name = 'simple-keyword-vector'

    @staticmethod
    def _sparse_vector(text: str) -> dict[str, float]:
        vector: dict[str, float] = {}
        for token in extract_keywords(text):
            vector[token] = vector.get(token, 0.0) + 1.0
        return vector

    @staticmethod
    def _cosine_similarity(left_vector: dict[str, float], right_vector: dict[str, float]) -> float:
        if not left_vector or not right_vector:
            return 0.0
        dot_product = sum(left_vector.get(key, 0.0) * right_vector.get(key, 0.0) for key in set(left_vector) | set(right_vector))
        left_norm = math.sqrt(sum(value * value for value in left_vector.values()))
        right_norm = math.sqrt(sum(value * value for value in right_vector.values()))
        if not left_norm or not right_norm:
            return 0.0
        return dot_product / (left_norm * right_norm)

    def score_documents(
        self,
        query: str,
        documents: list[VectorDocument],
        top_k: int | None = None,
        *,
        database: Session | None = None,
    ) -> list[VectorMatch]:
        query_vector = self._sparse_vector(query)
        matches = [
            VectorMatch(
                document_id=document.document_id,
                score=round(self._cosine_similarity(query_vector, self._sparse_vector(document.text)), 6),
                metadata=document.metadata,
            )
            for document in documents
        ]
        matches.sort(key=lambda item: item.score, reverse=True)
        if top_k is not None:
            return matches[:top_k]
        return matches


class EmbeddingGatewayError(RuntimeError):
    pass


class EmbeddingVectorBackend(VectorBackend):
    backend_name = 'openai-compatible-embedding'

    def __init__(self, settings: AppSettings, *, urlopen=None):
        if not settings.embedding_configured:
            raise ValueError('embedding backend requires AICODING_EMBEDDING_BASE_URL, API_KEY and MODEL')
        self.settings = settings
        self.urlopen = urlopen or urllib.request.urlopen
        self.fallback_backend = SimpleKeywordVectorBackend()

    @staticmethod
    def _cosine_similarity(left_vector: list[float], right_vector: list[float]) -> float:
        if not left_vector or not right_vector or len(left_vector) != len(right_vector):
            return 0.0
        dot_product = sum(left * right for left, right in zip(left_vector, right_vector))
        left_norm = math.sqrt(sum(value * value for value in left_vector))
        right_norm = math.sqrt(sum(value * value for value in right_vector))
        if not left_norm or not right_norm:
            return 0.0
        return dot_product / (left_norm * right_norm)

    def _request_embeddings(self, inputs: list[str]) -> list[list[float]]:
        payload = json.dumps({'model': self.settings.embedding_model, 'input': inputs}).encode('utf-8')
        request = urllib.request.Request(
            f'{self.settings.embedding_base_url}{self.settings.embedding_path}',
            data=payload,
            headers={
                'Authorization': f'Bearer {self.settings.embedding_api_key}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
            method='POST',
        )
        try:
            with self.urlopen(request, timeout=self.settings.embedding_timeout_sec) as response:
                raw_payload = json.loads(response.read().decode('utf-8', 'replace'))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode('utf-8', 'replace')
            raise EmbeddingGatewayError(detail or str(exc)) from exc
        except urllib.error.URLError as exc:
            raise EmbeddingGatewayError(str(exc.reason)) from exc

        data = raw_payload.get('data')
        if not isinstance(data, list):
            raise EmbeddingGatewayError('embedding response missing data list')
        ordered_embeddings = sorted(data, key=lambda item: item.get('index', 0))
        embeddings = [item.get('embedding') for item in ordered_embeddings]
        if any(not isinstance(item, list) for item in embeddings):
            raise EmbeddingGatewayError('embedding response contains invalid vectors')
        return embeddings

    def score_documents(
        self,
        query: str,
        documents: list[VectorDocument],
        top_k: int | None = None,
        *,
        database: Session | None = None,
    ) -> list[VectorMatch]:
        if not documents:
            return []
        try:
            embeddings = self._request_embeddings([query] + [document.text for document in documents])
        except EmbeddingGatewayError:
            return self.fallback_backend.score_documents(query, documents, top_k=top_k)
        query_embedding = embeddings[0]
        document_embeddings = embeddings[1:]
        matches = [
            VectorMatch(
                document_id=document.document_id,
                score=round(self._cosine_similarity(query_embedding, embedding), 6),
                metadata=document.metadata,
            )
            for document, embedding in zip(documents, document_embeddings)
        ]
        matches.sort(key=lambda item: item.score, reverse=True)
        if top_k is not None:
            return matches[:top_k]
        return matches


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


def build_knowledge_vector_document(item: KnowledgeItem) -> VectorDocument:
    return VectorDocument(
        document_id=item.knowledge_id,
        text=build_knowledge_text(item),
        metadata={
            'entity_type': 'knowledge',
            'entity_id': item.knowledge_id,
            'tenant_id': item.tenant_id,
            'team_id': item.team_id,
            'scope_type': item.scope_type,
            'scope_id': item.scope_id,
            'knowledge_type': item.knowledge_type,
            'title': item.title,
            'content': item.content.get('conclusion') or item.content.get('summary') or '',
        },
    )


def build_config_rule_text(profile: ConfigProfile, instruction: str) -> str:
    return ' '.join([profile.profile_type or 'prompt', profile.scope_type, profile.scope_id, instruction])


def build_config_vector_documents(profile: ConfigProfile) -> list[VectorDocument]:
    instructions = profile.content.get('instructions', []) if profile.content else []
    documents: list[VectorDocument] = []
    for index, instruction in enumerate(instructions, start=1):
        documents.append(
            VectorDocument(
                document_id=f'config:{profile.profile_id}:{index}',
                text=build_config_rule_text(profile, instruction),
                metadata={
                    'entity_type': 'config_profile',
                    'entity_id': profile.profile_id,
                    'tenant_id': profile.tenant_id,
                    'team_id': profile.team_id,
                    'scope_type': profile.scope_type,
                    'scope_id': profile.scope_id,
                    'profile_id': profile.profile_id,
                    'profile_type': profile.profile_type,
                    'rule_index': index,
                    'content': instruction,
                },
            )
        )
    return documents


def _document_hash(document: VectorDocument, embedding_model: str) -> str:
    return hashlib.sha256(f'{embedding_model}\n{document.text}'.encode('utf-8')).hexdigest()


class PersistentPgVectorBackend(VectorBackend):
    backend_name = 'pgvector-persistent-store'

    def __init__(self, settings: AppSettings, *, urlopen=None):
        self.settings = settings
        self.embedding_backend = EmbeddingVectorBackend(settings, urlopen=urlopen) if settings.embedding_configured else None
        self.fallback_backend = SimpleKeywordVectorBackend()

    @staticmethod
    def _cosine_similarity(left_vector: list[float], right_vector: list[float]) -> float:
        return EmbeddingVectorBackend._cosine_similarity(left_vector, right_vector)

    @staticmethod
    def _supports_native_pgvector(database: Session | None) -> bool:
        if not database or not getattr(database, 'bind', None):
            return False
        return database.bind.dialect.name == 'postgresql'

    def _persist_documents(self, database: Session, documents: list[VectorDocument]) -> dict[str, list[float]]:
        if not self.embedding_backend:
            return {}

        existing_entries = {
            entry.document_id: entry
            for entry in database.scalars(
                select(VectorIndexEntry).where(VectorIndexEntry.document_id.in_([document.document_id for document in documents]))
            ).all()
        }
        missing_or_stale = [
            document
            for document in documents
            if document.document_id not in existing_entries
            or existing_entries[document.document_id].content_hash
            != _document_hash(document, self.settings.embedding_model or 'unknown')
        ]
        if missing_or_stale:
            embeddings = self.embedding_backend._request_embeddings([document.text for document in missing_or_stale])
            for document, embedding in zip(missing_or_stale, embeddings):
                payload_metadata = dict(document.metadata)
                entry = existing_entries.get(document.document_id)
                if not entry:
                    entry = VectorIndexEntry(
                        document_id=document.document_id,
                        entity_type=payload_metadata.get('entity_type', 'knowledge'),
                        entity_id=payload_metadata.get('entity_id', document.document_id),
                        tenant_id=payload_metadata.get('tenant_id'),
                        team_id=payload_metadata.get('team_id'),
                        scope_type=payload_metadata.get('scope_type'),
                        scope_id=payload_metadata.get('scope_id'),
                        content_hash=_document_hash(document, self.settings.embedding_model or 'unknown'),
                        embedding_model=self.settings.embedding_model or 'unknown',
                        source_text=document.text,
                        vector=embedding,
                        document_metadata=payload_metadata,
                    )
                    database.add(entry)
                    existing_entries[document.document_id] = entry
                else:
                    entry.entity_type = payload_metadata.get('entity_type', entry.entity_type)
                    entry.entity_id = payload_metadata.get('entity_id', entry.entity_id)
                    entry.tenant_id = payload_metadata.get('tenant_id')
                    entry.team_id = payload_metadata.get('team_id')
                    entry.scope_type = payload_metadata.get('scope_type')
                    entry.scope_id = payload_metadata.get('scope_id')
                    entry.content_hash = _document_hash(document, self.settings.embedding_model or 'unknown')
                    entry.embedding_model = self.settings.embedding_model or 'unknown'
                    entry.source_text = document.text
                    entry.vector = embedding
                    entry.document_metadata = payload_metadata
            database.flush()
        return {document_id: entry.vector for document_id, entry in existing_entries.items()}

    def _score_documents_with_native_pgvector(
        self,
        database: Session,
        documents: list[VectorDocument],
        query_vector: list[float],
        *,
        top_k: int | None = None,
    ) -> list[VectorMatch]:
        if PgVector is None:
            raise ValueError('pgvector backend requires the pgvector package to be installed')
        vector_column = cast(VectorIndexEntry.vector, PgVector(self.settings.vector_dimensions))
        distance = vector_column.cosine_distance(query_vector)
        statement = (
            select(
                VectorIndexEntry.document_id,
                VectorIndexEntry.document_metadata,
                distance.label('distance'),
            )
            .where(VectorIndexEntry.document_id.in_([document.document_id for document in documents]))
            .order_by(distance.asc())
        )
        if top_k is not None:
            statement = statement.limit(top_k)

        matches: list[VectorMatch] = []
        for document_id, metadata, distance_value in database.execute(statement).all():
            normalized_score = round(max(0.0, 1 - float(distance_value or 0.0)), 6)
            matches.append(
                VectorMatch(
                    document_id=document_id,
                    score=normalized_score,
                    metadata=metadata or {},
                )
            )
        return matches

    def score_documents(
        self,
        query: str,
        documents: list[VectorDocument],
        top_k: int | None = None,
        *,
        database: Session | None = None,
        ) -> list[VectorMatch]:
        if not documents:
            return []
        if not database or not self.embedding_backend:
            return self.fallback_backend.score_documents(query, documents, top_k=top_k)
        try:
            document_vectors = self._persist_documents(database, documents)
            query_vector = self.embedding_backend._request_embeddings([query])[0]
        except EmbeddingGatewayError:
            return self.fallback_backend.score_documents(query, documents, top_k=top_k)

        if self._supports_native_pgvector(database):
            return self._score_documents_with_native_pgvector(
                database,
                documents,
                query_vector,
                top_k=top_k,
            )

        matches = [
            VectorMatch(
                document_id=document.document_id,
                score=round(self._cosine_similarity(query_vector, document_vectors.get(document.document_id, [])), 6),
                metadata=document.metadata,
            )
            for document in documents
        ]
        matches.sort(key=lambda item: item.score, reverse=True)
        if top_k is not None:
            return matches[:top_k]
        return matches


def sync_knowledge_vector_index(database: Session, knowledge: KnowledgeItem, *, settings: AppSettings | None = None, urlopen=None) -> None:
    app_settings = settings or load_settings()
    if app_settings.vector_backend.lower() not in {'pgvector', 'postgres'}:
        return
    database.execute(delete(VectorIndexEntry).where(VectorIndexEntry.document_id == knowledge.knowledge_id))
    if knowledge.status != 'active':
        database.flush()
        return
    backend = PersistentPgVectorBackend(app_settings, urlopen=urlopen)
    if not backend.embedding_backend:
        database.flush()
        return
    backend._persist_documents(database, [build_knowledge_vector_document(knowledge)])


def sync_config_vector_index(database: Session, profile: ConfigProfile, *, settings: AppSettings | None = None, urlopen=None) -> None:
    app_settings = settings or load_settings()
    if app_settings.vector_backend.lower() not in {'pgvector', 'postgres'}:
        return
    database.execute(
        delete(VectorIndexEntry).where(
            VectorIndexEntry.entity_type == 'config_profile',
            VectorIndexEntry.entity_id == profile.profile_id,
        )
    )
    if profile.status != 'active':
        database.flush()
        return
    documents = build_config_vector_documents(profile)
    if not documents:
        database.flush()
        return
    backend = PersistentPgVectorBackend(app_settings, urlopen=urlopen)
    if not backend.embedding_backend:
        database.flush()
        return
    backend._persist_documents(database, documents)


def create_vector_backend(*, settings: AppSettings | None = None, urlopen=None) -> VectorBackend:
    app_settings = settings or load_settings()
    backend_name = app_settings.vector_backend.lower()
    if backend_name in {'simple', 'keyword', 'simple-keyword'}:
        return SimpleKeywordVectorBackend()
    if backend_name in {'embedding'}:
        return EmbeddingVectorBackend(app_settings, urlopen=urlopen)
    if backend_name in {'pgvector', 'postgres'}:
        if PgVector is None:
            raise ValueError('pgvector backend requires the pgvector package to be installed')
        return PersistentPgVectorBackend(app_settings, urlopen=urlopen)
    return SimpleKeywordVectorBackend()
