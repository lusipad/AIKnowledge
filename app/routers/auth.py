from fastapi import APIRouter, Depends, Request

from app.request_context import get_request_context
from app.security import require_min_role
from app.utils import api_response


router = APIRouter(prefix="/api/v1", tags=["auth"])


@router.get("/auth/identity")
def get_identity(
    request: Request,
    _: str = Depends(require_min_role('viewer')),
):
    request_context = get_request_context()
    return api_response(
        {
            'source': getattr(request.state, 'authenticated_source', 'anonymous'),
            'user_id': request_context.user_id,
            'user_role': request_context.user_role,
            'tenant_id': request_context.tenant_id,
            'team_id': request_context.team_id,
            'allowed_tenant_ids': getattr(request.state, 'allowed_tenant_ids', []),
            'allowed_team_ids': getattr(request.state, 'allowed_team_ids', []),
        }
    )
