from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from dataclasses import dataclass

from app.settings import AppSettings, load_settings
from app.utils import extract_keywords


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

    def score_documents(self, query: str, documents: list[VectorDocument], top_k: int | None = None) -> list[VectorMatch]:
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

    def score_documents(self, query: str, documents: list[VectorDocument], top_k: int | None = None) -> list[VectorMatch]:
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


class PgVectorPlaceholderBackend(SimpleKeywordVectorBackend):
    backend_name = 'pgvector-placeholder'


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

    def score_documents(self, query: str, documents: list[VectorDocument], top_k: int | None = None) -> list[VectorMatch]:
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



def create_vector_backend(*, settings: AppSettings | None = None, urlopen=None) -> VectorBackend:
    app_settings = settings or load_settings()
    backend_name = app_settings.vector_backend.lower()
    if backend_name in {'simple', 'keyword', 'simple-keyword'}:
        return SimpleKeywordVectorBackend()
    if backend_name in {'embedding'}:
        return EmbeddingVectorBackend(app_settings, urlopen=urlopen)
    if backend_name in {'pgvector', 'postgres'}:
        return PgVectorPlaceholderBackend()
    return SimpleKeywordVectorBackend()
