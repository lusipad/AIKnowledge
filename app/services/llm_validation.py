from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Callable

from app.settings import AppSettings


UrlopenType = Callable[..., object]


class LlmGatewayError(RuntimeError):
    def __init__(self, error: str, detail: str, status_code: int | None = None):
        super().__init__(detail)
        self.error = error
        self.detail = detail
        self.status_code = status_code


@dataclass
class ChatCompletionResponse:
    status_code: int
    duration_ms: int
    payload: dict
    response_text: str


@dataclass
class LlmVerificationResult:
    ok: bool
    configured: bool
    base_url: str | None
    chat_path: str
    model: str | None
    status_code: int | None
    duration_ms: int
    response_text: str | None = None
    error: str | None = None
    detail: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def build_chat_completions_url(settings: AppSettings) -> str | None:
    if not settings.llm_base_url:
        return None
    return f"{settings.llm_base_url}{settings.llm_chat_path}"


def extract_chat_completion_text(payload: dict) -> str:
    choices = payload.get('choices') or []
    if not choices:
        return ''

    message = choices[0].get('message') or {}
    content = message.get('content')
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get('type') == 'text':
                text_parts.append(str(item.get('text', '')).strip())
        return '\n'.join(part for part in text_parts if part)
    return str(content or '').strip()


def request_chat_completion(
    settings: AppSettings,
    *,
    messages: list[dict],
    max_tokens: int = 256,
    temperature: float = 0,
    urlopen: UrlopenType = urllib.request.urlopen,
) -> ChatCompletionResponse:
    start_time = time.perf_counter()
    url = build_chat_completions_url(settings)
    if not settings.llm_configured or not url:
        raise LlmGatewayError(
            error='llm_not_configured',
            detail='Set AICODING_LLM_BASE_URL, AICODING_LLM_API_KEY, and AICODING_LLM_MODEL first.',
            status_code=None,
        )

    payload = {
        'model': settings.llm_model,
        'messages': messages,
        'max_tokens': max(1, max_tokens),
        'temperature': temperature,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {settings.llm_api_key}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )

    try:
        with urlopen(request, timeout=settings.llm_timeout_sec) as response:
            raw_body = response.read().decode('utf-8', 'replace')
            parsed_body = json.loads(raw_body)
            duration_ms = round((time.perf_counter() - start_time) * 1000)
            return ChatCompletionResponse(
                status_code=getattr(response, 'status', 200),
                duration_ms=duration_ms,
                payload=parsed_body,
                response_text=extract_chat_completion_text(parsed_body),
            )
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode('utf-8', 'replace')
        close_method = getattr(exc, 'close', None)
        if callable(close_method):
            close_method()
        raise LlmGatewayError(
            error='upstream_http_error',
            detail=error_body[:1000] or str(exc),
            status_code=exc.code,
        ) from exc
    except json.JSONDecodeError as exc:
        raise LlmGatewayError(
            error='invalid_json_response',
            detail=str(exc),
            status_code=None,
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive path
        raise LlmGatewayError(
            error='request_failed',
            detail=str(exc),
            status_code=None,
        ) from exc


def verify_llm_connection(
    settings: AppSettings,
    prompt: str = 'Reply with ok only.',
    max_tokens: int = 32,
    urlopen: UrlopenType = urllib.request.urlopen,
) -> LlmVerificationResult:
    start_time = time.perf_counter()
    if not settings.llm_configured:
        duration_ms = round((time.perf_counter() - start_time) * 1000)
        return LlmVerificationResult(
            ok=False,
            configured=False,
            base_url=settings.llm_base_url,
            chat_path=settings.llm_chat_path,
            model=settings.llm_model,
            status_code=None,
            duration_ms=duration_ms,
            error='llm_not_configured',
            detail='Set AICODING_LLM_BASE_URL, AICODING_LLM_API_KEY, and AICODING_LLM_MODEL first.',
        )

    try:
        completion = request_chat_completion(
            settings,
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=max_tokens,
            temperature=0,
            urlopen=urlopen,
        )
        return LlmVerificationResult(
            ok=True,
            configured=True,
            base_url=settings.llm_base_url,
            chat_path=settings.llm_chat_path,
            model=settings.llm_model,
            status_code=completion.status_code,
            duration_ms=completion.duration_ms,
            response_text=completion.response_text[:500] or None,
            detail='chat_completions_ok',
        )
    except LlmGatewayError as exc:
        duration_ms = round((time.perf_counter() - start_time) * 1000)
        return LlmVerificationResult(
            ok=False,
            configured=True,
            base_url=settings.llm_base_url,
            chat_path=settings.llm_chat_path,
            model=settings.llm_model,
            status_code=exc.status_code,
            duration_ms=duration_ms,
            error=exc.error,
            detail=exc.detail,
        )
