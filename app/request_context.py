from __future__ import annotations

import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


@dataclass(frozen=True)
class RequestContext:
    request_id: str
    tenant_id: str | None = None
    team_id: str | None = None
    user_id: str | None = None
    client_type: str | None = None


_request_context_var: ContextVar[RequestContext] = ContextVar(
    'request_context',
    default=RequestContext(request_id='req_unknown'),
)


def _build_request_context(request: Request) -> RequestContext:
    return RequestContext(
        request_id=request.headers.get('X-Request-Id') or f'req_{uuid.uuid4().hex[:12]}',
        tenant_id=request.headers.get('X-Tenant-Id') or None,
        team_id=request.headers.get('X-Team-Id') or None,
        user_id=request.headers.get('X-User-Id') or None,
        client_type=request.headers.get('X-Client-Type') or None,
    )


def set_request_context(request_context: RequestContext) -> Token:
    return _request_context_var.set(request_context)


def reset_request_context(token: Token) -> None:
    _request_context_var.reset(token)


def get_request_context() -> RequestContext:
    return _request_context_var.get()


def get_request_id() -> str:
    return get_request_context().request_id


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_context = _build_request_context(request)
        token = set_request_context(request_context)
        request.state.request_context = request_context
        try:
            response = await call_next(request)
        finally:
            reset_request_context(token)

        response.headers['X-Request-Id'] = request_context.request_id
        return response
