from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import AuditLog
from app.security import require_min_role
from app.services.isolation import apply_audit_scope
from app.utils import api_response


router = APIRouter(prefix="/api/v1", tags=["audit"])


@router.get("/audit/logs")
def list_audit_logs(
    action: str | None = None,
    resource_type: str | None = None,
    limit: int = 100,
    database: Session = Depends(get_db),
    _: str = Depends(require_min_role('viewer')),
):
    statement = apply_audit_scope(select(AuditLog).order_by(AuditLog.created_at.desc()))
    if action:
        statement = statement.where(AuditLog.action == action)
    if resource_type:
        statement = statement.where(AuditLog.resource_type == resource_type)
    statement = statement.limit(max(1, min(limit, 500)))

    logs = database.scalars(statement).all()
    return api_response(
        [
            {
                "audit_id": log.audit_id,
                "actor_id": log.actor_id,
                "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "scope_type": log.scope_type,
                "scope_id": log.scope_id,
                "detail": log.detail,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ]
    )
