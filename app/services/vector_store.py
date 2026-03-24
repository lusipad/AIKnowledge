from __future__ import annotations

import math
import os
from dataclasses import dataclass

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



def create_vector_backend() -> VectorBackend:
    backend_name = os.getenv('AICODING_VECTOR_BACKEND', 'simple').lower()
    if backend_name in {'simple', 'keyword', 'simple-keyword'}:
        return SimpleKeywordVectorBackend()
    if backend_name in {'pgvector', 'postgres'}:
        return PgVectorPlaceholderBackend()
    return SimpleKeywordVectorBackend()
