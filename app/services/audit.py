from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AuditLog
from app.request_context import get_request_context


def append_audit_log(
    database: Session,
    *,
    actor_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    scope_type: str | None = None,
    scope_id: str | None = None,
    detail: dict | None = None,
) -> None:
    request_context = get_request_context()
    payload_detail = dict(detail or {})
    payload_detail.setdefault('request_id', request_context.request_id)
    if request_context.client_type:
        payload_detail.setdefault('client_type', request_context.client_type)
    if request_context.user_role:
        payload_detail.setdefault('user_role', request_context.user_role)
    if request_context.tenant_id:
        payload_detail.setdefault('tenant_id', request_context.tenant_id)
    if request_context.team_id:
        payload_detail.setdefault('team_id', request_context.team_id)

    database.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            scope_type=scope_type,
            scope_id=scope_id,
            detail=payload_detail,
        )
    )
