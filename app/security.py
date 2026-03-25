from __future__ import annotations

from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.settings import ALLOWED_USER_ROLES


EXEMPT_PATHS = {
    '/',
    '/healthz',
    '/readyz',
    '/console',
    '/console/',
    '/docs',
    '/openapi.json',
    '/redoc',
    '/favicon.ico',
}

EXEMPT_PREFIXES = (
    '/docs',
    '/redoc',
    '/openapi',
    '/static/console/',
)

ROLE_RANK = {
    'viewer': 10,
    'writer': 20,
    'reviewer': 30,
    'admin': 40,
}


def is_exempt_path(path: str) -> bool:
    if path in EXEMPT_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in EXEMPT_PREFIXES)


def extract_api_key(request: Request) -> str | None:
    explicit_key = request.headers.get('x-api-key')
    if explicit_key:
        return explicit_key

    auth_header = request.headers.get('authorization', '')
    if auth_header.lower().startswith('bearer '):
        return auth_header[7:].strip()
    return None


def resolve_request_role(request: Request, *, default_role: str = 'admin') -> str:
    authenticated_role = getattr(request.state, 'authenticated_role', None)
    requested_role = (request.headers.get('X-User-Role') or '').strip().lower()
    role = authenticated_role or requested_role or default_role
    return role if role in ALLOWED_USER_ROLES else default_role


def require_min_role(min_role: str):
    minimum_rank = ROLE_RANK[min_role]

    def dependency(request: Request) -> str:
        resolved_role = resolve_request_role(request)
        if ROLE_RANK.get(resolved_role, 0) < minimum_rank:
            raise HTTPException(status_code=403, detail='insufficient role permissions')
        return resolved_role

    return dependency


class ApiKeyMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        api_keys: tuple[str, ...] | list[str] | set[str],
        *,
        api_key_roles: dict[str, str] | None = None,
    ):
        super().__init__(app)
        self.api_keys = {key for key in api_keys if key}
        self.api_key_roles = dict(api_key_roles or {})

    async def dispatch(self, request: Request, call_next):
        if is_exempt_path(request.url.path):
            return await call_next(request)

        provided_key = extract_api_key(request)
        if not provided_key or provided_key not in self.api_keys:
            return JSONResponse(
                status_code=401,
                content={'code': 401100, 'message': 'unauthorized', 'data': {}},
            )
        request.state.authenticated_role = self.api_key_roles.get(provided_key)
        return await call_next(request)
