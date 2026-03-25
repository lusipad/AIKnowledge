from __future__ import annotations

from typing import Iterable

from app.request_context import RequestContext


ACL_KEYS = ('owners', 'editors', 'reviewers', 'viewers')

DEFAULT_VIEWER_PRINCIPALS = ['role:viewer', 'role:writer', 'role:reviewer', 'role:admin']
DEFAULT_REVIEWER_PRINCIPALS = ['role:reviewer', 'role:admin']
DEFAULT_EDITOR_PRINCIPALS = ['role:admin']


def normalize_acl(acl: dict | None) -> dict[str, list[str]]:
    normalized: dict[str, list[str]] = {key: [] for key in ACL_KEYS}
    raw_acl = acl or {}
    for key in ACL_KEYS:
        values = raw_acl.get(key, [])
        if not isinstance(values, list):
            continue
        normalized[key] = list(dict.fromkeys([str(item).strip() for item in values if str(item).strip()]))
    return normalized


def has_acl_entries(acl: dict | None) -> bool:
    normalized = normalize_acl(acl)
    return any(normalized[key] for key in ACL_KEYS)


def _principals(request_context: RequestContext) -> set[str]:
    principals: set[str] = set()
    if request_context.user_id:
        principals.add(request_context.user_id)
    if request_context.user_role:
        principals.add(f'role:{request_context.user_role}')
    return principals


def _matches(allowed_principals: Iterable[str], request_context: RequestContext) -> bool:
    current_principals = _principals(request_context)
    if not current_principals:
        return False
    return bool(current_principals & set(allowed_principals))


def default_knowledge_acl(owner_id: str | None) -> dict[str, list[str]]:
    acl = normalize_acl(
        {
            'owners': [owner_id] if owner_id else [],
            'editors': DEFAULT_EDITOR_PRINCIPALS,
            'reviewers': DEFAULT_REVIEWER_PRINCIPALS,
            'viewers': DEFAULT_VIEWER_PRINCIPALS,
        }
    )
    return acl


def default_config_acl(owner_id: str | None) -> dict[str, list[str]]:
    acl = normalize_acl(
        {
            'owners': [owner_id] if owner_id else [],
            'editors': DEFAULT_EDITOR_PRINCIPALS,
            'reviewers': [],
            'viewers': DEFAULT_VIEWER_PRINCIPALS,
        }
    )
    return acl


def can_view_resource(acl: dict | None, request_context: RequestContext) -> bool:
    if not has_acl_entries(acl):
        return True
    normalized = normalize_acl(acl)
    allowed = normalized['viewers'] + normalized['reviewers'] + normalized['editors'] + normalized['owners']
    return _matches(allowed, request_context)


def can_review_resource(acl: dict | None, request_context: RequestContext) -> bool:
    if not has_acl_entries(acl):
        return True
    normalized = normalize_acl(acl)
    allowed = normalized['reviewers'] + normalized['owners']
    return _matches(allowed, request_context)


def can_edit_resource(acl: dict | None, request_context: RequestContext) -> bool:
    if not has_acl_entries(acl):
        return True
    normalized = normalize_acl(acl)
    allowed = normalized['editors'] + normalized['owners']
    return _matches(allowed, request_context)
