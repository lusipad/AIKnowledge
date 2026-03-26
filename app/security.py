from __future__ import annotations

from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.settings import ALLOWED_USER_ROLES
from app.services.iam import IamAuthenticationError, synchronize_identity_scope, verify_bearer_token
from app.settings import load_settings


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


def extract_bearer_token(request: Request) -> str | None:
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


class AuthenticationMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        api_keys: tuple[str, ...] | list[str] | set[str],
        *,
        api_key_roles: dict[str, str] | None = None,
        settings=None,
    ):
        super().__init__(app)
        self.api_keys = {key for key in api_keys if key}
        self.api_key_roles = dict(api_key_roles or {})
        self.settings = settings or load_settings()

    async def dispatch(self, request: Request, call_next):
        if is_exempt_path(request.url.path):
            return await call_next(request)

        bearer_token = extract_bearer_token(request)
        provided_key = extract_api_key(request)
        if provided_key and provided_key in self.api_keys:
            request.state.authenticated_role = self.api_key_roles.get(provided_key)
            request.state.authenticated_source = 'api_key'
            return await call_next(request)

        if self.settings.iam_enabled and bearer_token:
            try:
                identity = synchronize_identity_scope(
                    verify_bearer_token(bearer_token, settings=self.settings),
                    requested_tenant_id=request.headers.get('X-Tenant-Id') or None,
                    requested_team_id=request.headers.get('X-Team-Id') or None,
                )
            except IamAuthenticationError as exc:
                status_code = 403 if 'not granted' in str(exc) else 401
                return JSONResponse(
                    status_code=status_code,
                    content={'code': 403100 if status_code == 403 else 401100, 'message': str(exc), 'data': {}},
                )
            request.state.authenticated_source = identity.source
            request.state.authenticated_identity = identity
            request.state.authenticated_role = identity.user_role
            request.state.authenticated_user_id = identity.user_id
            request.state.authenticated_tenant_id = identity.tenant_id
            request.state.authenticated_team_id = identity.team_id
            request.state.allowed_tenant_ids = list(identity.allowed_tenant_ids)
            request.state.allowed_team_ids = list(identity.allowed_team_ids)
            request.state.directory_group_ids = list(identity.directory_group_ids)
            request.state.authenticated_claims = identity.claims
            return await call_next(request)

        if self.api_keys or self.settings.iam_enabled:
            return JSONResponse(
                status_code=401,
                content={'code': 401100, 'message': 'unauthorized', 'data': {}},
            )
        return await call_next(request)
