from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


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


class ApiKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, api_key: str):
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request: Request, call_next):
        if is_exempt_path(request.url.path):
            return await call_next(request)

        provided_key = extract_api_key(request)
        if not provided_key or provided_key != self.api_key:
            return JSONResponse(
                status_code=401,
                content={'code': 401100, 'message': 'unauthorized', 'data': {}},
            )
        return await call_next(request)
