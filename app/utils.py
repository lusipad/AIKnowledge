from __future__ import annotations

import json
import re
import uuid
from difflib import SequenceMatcher
from typing import Any

from app.request_context import get_request_id


def generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def api_response(data: Any = None, message: str = "ok", code: int = 0, request_id: str | None = None) -> dict[str, Any]:
    payload = {"code": code, "message": message, "data": data or {}}
    resolved_request_id = request_id or get_request_id()
    if resolved_request_id:
        payload["request_id"] = resolved_request_id
    return payload


def to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def extract_keywords(text: str) -> list[str]:
    normalized_text = (text or "").lower().strip()
    raw_tokens = re.findall(r"[a-z0-9_./-]+|[\u4e00-\u9fff]{2,}", normalized_text)
    keywords: list[str] = []
    for token in raw_tokens:
        if len(token) >= 2:
            keywords.append(token)
        if re.fullmatch(r"[\u4e00-\u9fff]{4,}", token):
            for index in range(len(token) - 1):
                keywords.append(token[index : index + 2])
    return list(dict.fromkeys(keywords))


def keyword_overlap_score(query: str, document: str) -> float:
    query_keywords = extract_keywords(query)
    document_text = (document or "").lower()
    if not query_keywords:
        return 0.0
    hits = sum(1 for keyword in query_keywords if keyword in document_text)
    return hits / len(query_keywords)


def similarity_score(left_text: str, right_text: str) -> float:
    return SequenceMatcher(None, (left_text or "").lower(), (right_text or "").lower()).ratio()

