from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from app.utils import generate_id


class AiKnowledgeClientError(RuntimeError):
    def __init__(self, status_code: int | None, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass
class AiKnowledgeClient:
    base_url: str
    api_key: str | None = None
    tenant_id: str | None = None
    team_id: str | None = None
    user_id: str | None = None
    user_role: str | None = None
    client_type: str = 'cli'
    timeout_sec: int = 30

    def _headers(self, request_id: str | None = None) -> dict[str, str]:
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'X-Client-Type': self.client_type,
            'X-Request-Id': request_id or generate_id('req'),
        }
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        if self.tenant_id:
            headers['X-Tenant-Id'] = self.tenant_id
        if self.team_id:
            headers['X-Team-Id'] = self.team_id
        if self.user_id:
            headers['X-User-Id'] = self.user_id
        if self.user_role:
            headers['X-User-Role'] = self.user_role
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        base = self.base_url.rstrip('/')
        url = f'{base}/{path.lstrip("/")}'
        if query:
            encoded_query = urllib.parse.urlencode({key: value for key, value in query.items() if value is not None}, doseq=True)
            if encoded_query:
                url = f'{url}?{encoded_query}'

        body = json.dumps(payload).encode('utf-8') if payload is not None else None
        request = urllib.request.Request(url, data=body, headers=self._headers(), method=method.upper())
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_sec) as response:
                return json.loads(response.read().decode('utf-8', 'replace'))
        except urllib.error.HTTPError as exc:
            response_text = exc.read().decode('utf-8', 'replace')
            close_method = getattr(exc, 'close', None)
            if callable(close_method):
                close_method()
            raise AiKnowledgeClientError(exc.code, response_text or str(exc)) from exc
        except urllib.error.URLError as exc:
            raise AiKnowledgeClientError(None, str(exc.reason)) from exc

    def create_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request('POST', '/api/v1/sessions', payload=payload)

    def list_sessions(self, **query: Any) -> dict[str, Any]:
        return self.request('GET', '/api/v1/sessions', query=query)

    def append_context_events(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request('POST', '/api/v1/context/events', payload=payload)

    def list_signals(self, *, status: str | None = None) -> dict[str, Any]:
        return self.request('GET', '/api/v1/signals', query={'status': status})

    def create_extract_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request('POST', '/api/v1/knowledge/extract', payload=payload)

    def get_extract_task(self, task_id: str) -> dict[str, Any]:
        return self.request('GET', f'/api/v1/knowledge/extract/{task_id}')

    def review_knowledge(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request('POST', '/api/v1/knowledge/review', payload=payload)

    def retrieve_context_pack(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request('POST', '/api/v1/retrieval/query', payload=payload)

    def list_retrieval_logs(self, **query: Any) -> dict[str, Any]:
        return self.request('GET', '/api/v1/retrieval/logs', query=query)

    def get_retrieval_log(self, request_id: str) -> dict[str, Any]:
        return self.request('GET', f'/api/v1/retrieval/logs/{request_id}')

    def submit_knowledge_feedback(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request('POST', '/api/v1/feedback/knowledge', payload=payload)

    def submit_context_pack_feedback(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request('POST', '/api/v1/feedback/context-pack', payload=payload)

    def list_knowledge(self, **query: Any) -> dict[str, Any]:
        return self.request('GET', '/api/v1/knowledge', query=query)

    def get_knowledge(self, knowledge_id: str) -> dict[str, Any]:
        return self.request('GET', f'/api/v1/knowledge/{knowledge_id}')

    def list_evaluation_scenarios(self) -> dict[str, Any]:
        return self.request('GET', '/api/v1/evaluation/scenarios')

    def run_evaluation(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request('POST', '/api/v1/evaluation/run', payload=payload)

    def list_evaluation_runs(self, **query: Any) -> dict[str, Any]:
        return self.request('GET', '/api/v1/evaluation/runs', query=query)

    def get_evaluation_run(self, run_id: str) -> dict[str, Any]:
        return self.request('GET', f'/api/v1/evaluation/runs/{run_id}')


def build_client_from_env() -> AiKnowledgeClient:
    base_url = os.getenv('AICODING_API_BASE_URL', 'http://127.0.0.1:8000')
    timeout_sec = max(1, int(os.getenv('AICODING_API_TIMEOUT_SEC', '30')))
    return AiKnowledgeClient(
        base_url=base_url,
        api_key=os.getenv('AICODING_API_KEY') or None,
        tenant_id=os.getenv('AICODING_TENANT_ID') or None,
        team_id=os.getenv('AICODING_TEAM_ID') or None,
        user_id=os.getenv('AICODING_USER_ID') or None,
        user_role=os.getenv('AICODING_USER_ROLE') or None,
        client_type=os.getenv('AICODING_CLIENT_TYPE', 'cli'),
        timeout_sec=timeout_sec,
    )
