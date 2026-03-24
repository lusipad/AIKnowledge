from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AuditLog


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
    database.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            scope_type=scope_type,
            scope_id=scope_id,
            detail=detail or {},
        )
    )
