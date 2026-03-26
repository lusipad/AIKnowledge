from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import DirectoryGroup, DirectoryGroupMembership, DirectoryUser
from app.request_context import RequestContext
from app.settings import ALLOWED_USER_ROLES


ALLOWED_DIRECTORY_SCOPE_TYPES = {'global', 'tenant', 'team'}


class DirectorySyncError(ValueError):
    pass


class DirectoryAuthorizationError(DirectorySyncError):
    pass


@dataclass(frozen=True)
class DirectoryResolvedAccess:
    user_active: bool | None
    directory_tenant_ids: tuple[str, ...]
    directory_team_ids: tuple[str, ...]
    directory_roles: tuple[str, ...]
    group_ids: tuple[str, ...]


def _unique_non_empty(values: list[str | None]) -> tuple[str, ...]:
    return tuple(dict.fromkeys([value for value in values if value]))


def _resolve_scope_id(scope_type: str, tenant_id: str | None, team_id: str | None, scope_id: str | None) -> str:
    normalized_scope_type = scope_type.lower().strip()
    if normalized_scope_type not in ALLOWED_DIRECTORY_SCOPE_TYPES:
        raise DirectorySyncError(f'unsupported directory scope_type: {scope_type}')
    if scope_id:
        return scope_id
    if normalized_scope_type == 'global':
        return 'global'
    if normalized_scope_type == 'tenant':
        if not tenant_id:
            raise DirectorySyncError('tenant scope directory group requires tenant_id')
        return f'tenant:{tenant_id}'
    if not tenant_id or not team_id:
        raise DirectorySyncError('team scope directory group requires tenant_id and team_id')
    return f'team:{tenant_id}:{team_id}'


def _resolve_role(mapped_role: str | None) -> str | None:
    if mapped_role is None:
        return None
    normalized_role = mapped_role.strip().lower()
    if not normalized_role:
        return None
    if normalized_role not in ALLOWED_USER_ROLES:
        raise DirectorySyncError(f'unsupported directory mapped_role: {mapped_role}')
    return normalized_role


def _resolve_payload_scope(
    payload_tenant_id: str | None,
    payload_team_id: str | None,
    request_context: RequestContext,
) -> tuple[str | None, str | None]:
    tenant_id = payload_tenant_id or request_context.tenant_id
    team_id = payload_team_id or request_context.team_id
    if request_context.tenant_id and tenant_id and tenant_id != request_context.tenant_id:
        raise DirectoryAuthorizationError('directory payload tenant_id is outside the active request scope')
    if request_context.team_id and team_id and team_id != request_context.team_id:
        raise DirectoryAuthorizationError('directory payload team_id is outside the active request scope')
    return tenant_id, team_id


def upsert_directory_user(
    database: Session,
    user_id: str,
    payload,
    request_context: RequestContext,
) -> DirectoryUser:
    tenant_id, team_id = _resolve_payload_scope(payload.tenant_id, payload.team_id, request_context)
    directory_user = database.get(DirectoryUser, user_id)
    if directory_user is None:
        directory_user = DirectoryUser(user_id=user_id)
        database.add(directory_user)
    directory_user.tenant_id = tenant_id
    directory_user.team_id = team_id
    directory_user.external_ref = payload.external_ref
    directory_user.email = payload.email
    directory_user.display_name = payload.display_name
    directory_user.active = payload.active
    directory_user.attributes = dict(payload.attributes)
    database.flush()
    return directory_user


def _ensure_directory_user(
    database: Session,
    user_id: str,
    *,
    tenant_id: str | None,
    team_id: str | None,
) -> DirectoryUser:
    directory_user = database.get(DirectoryUser, user_id)
    if directory_user is None:
        directory_user = DirectoryUser(
            user_id=user_id,
            tenant_id=tenant_id,
            team_id=team_id,
            active=True,
            attributes={},
        )
        database.add(directory_user)
        database.flush()
    return directory_user


def upsert_directory_group(
    database: Session,
    group_id: str,
    payload,
    request_context: RequestContext,
) -> DirectoryGroup:
    tenant_id, team_id = _resolve_payload_scope(payload.tenant_id, payload.team_id, request_context)
    scope_type = payload.scope_type.lower().strip()
    scope_id = _resolve_scope_id(scope_type, tenant_id, team_id, payload.scope_id)
    mapped_role = _resolve_role(payload.mapped_role)

    directory_group = database.get(DirectoryGroup, group_id)
    if directory_group is None:
        directory_group = DirectoryGroup(group_id=group_id)
        database.add(directory_group)

    directory_group.tenant_id = tenant_id
    directory_group.team_id = team_id
    directory_group.external_ref = payload.external_ref
    directory_group.display_name = payload.display_name
    directory_group.scope_type = scope_type
    directory_group.scope_id = scope_id
    directory_group.mapped_role = mapped_role
    directory_group.active = payload.active
    directory_group.attributes = dict(payload.attributes)
    database.flush()

    database.execute(delete(DirectoryGroupMembership).where(DirectoryGroupMembership.group_id == group_id))
    for member_user_id in dict.fromkeys([item.strip() for item in payload.member_user_ids if item.strip()]):
        _ensure_directory_user(database, member_user_id, tenant_id=tenant_id, team_id=team_id)
        database.add(DirectoryGroupMembership(group_id=group_id, user_id=member_user_id))
    database.flush()
    return directory_group


def sync_directory_snapshot(database: Session, payload, request_context: RequestContext) -> dict:
    synced_users: list[dict] = []
    synced_groups: list[dict] = []
    for user_id, user_payload in payload.users.items():
        synced_users.append(serialize_directory_user(upsert_directory_user(database, user_id, user_payload, request_context)))
    for group_id, group_payload in payload.groups.items():
        synced_groups.append(serialize_directory_group(database, upsert_directory_group(database, group_id, group_payload, request_context)))
    database.commit()
    return {
        'synced_users': synced_users,
        'synced_groups': synced_groups,
        'user_count': len(synced_users),
        'group_count': len(synced_groups),
    }


def serialize_directory_user(directory_user: DirectoryUser) -> dict:
    return {
        'user_id': directory_user.user_id,
        'tenant_id': directory_user.tenant_id,
        'team_id': directory_user.team_id,
        'external_ref': directory_user.external_ref,
        'email': directory_user.email,
        'display_name': directory_user.display_name,
        'active': directory_user.active,
        'attributes': directory_user.attributes,
        'updated_at': directory_user.updated_at.isoformat() if directory_user.updated_at else None,
    }


def serialize_directory_group(database: Session, directory_group: DirectoryGroup) -> dict:
    member_user_ids = database.scalars(
        select(DirectoryGroupMembership.user_id)
        .where(DirectoryGroupMembership.group_id == directory_group.group_id)
        .order_by(DirectoryGroupMembership.user_id.asc())
    ).all()
    return {
        'group_id': directory_group.group_id,
        'tenant_id': directory_group.tenant_id,
        'team_id': directory_group.team_id,
        'external_ref': directory_group.external_ref,
        'display_name': directory_group.display_name,
        'scope_type': directory_group.scope_type,
        'scope_id': directory_group.scope_id,
        'mapped_role': directory_group.mapped_role,
        'active': directory_group.active,
        'attributes': directory_group.attributes,
        'member_user_ids': member_user_ids,
        'updated_at': directory_group.updated_at.isoformat() if directory_group.updated_at else None,
    }


def list_directory_users(database: Session, request_context: RequestContext) -> list[dict]:
    statement = select(DirectoryUser).order_by(DirectoryUser.updated_at.desc(), DirectoryUser.user_id.asc())
    if request_context.tenant_id:
        statement = statement.where(DirectoryUser.tenant_id == request_context.tenant_id)
    if request_context.team_id:
        statement = statement.where(DirectoryUser.team_id == request_context.team_id)
    return [serialize_directory_user(item) for item in database.scalars(statement).all()]


def list_directory_groups(database: Session, request_context: RequestContext) -> list[dict]:
    statement = select(DirectoryGroup).order_by(DirectoryGroup.updated_at.desc(), DirectoryGroup.group_id.asc())
    if request_context.tenant_id:
        statement = statement.where(DirectoryGroup.tenant_id == request_context.tenant_id)
    if request_context.team_id:
        statement = statement.where(DirectoryGroup.team_id == request_context.team_id)
    return [serialize_directory_group(database, item) for item in database.scalars(statement).all()]


def resolve_directory_access(database: Session, user_id: str | None) -> DirectoryResolvedAccess:
    if not user_id:
        return DirectoryResolvedAccess(
            user_active=None,
            directory_tenant_ids=(),
            directory_team_ids=(),
            directory_roles=(),
            group_ids=(),
        )

    directory_user = database.get(DirectoryUser, user_id)
    groups = database.scalars(
        select(DirectoryGroup)
        .join(DirectoryGroupMembership, DirectoryGroupMembership.group_id == DirectoryGroup.group_id)
        .where(DirectoryGroupMembership.user_id == user_id, DirectoryGroup.active.is_(True))
        .order_by(DirectoryGroup.group_id.asc())
    ).all()
    return DirectoryResolvedAccess(
        user_active=directory_user.active if directory_user else None,
        directory_tenant_ids=_unique_non_empty(
            ([directory_user.tenant_id] if directory_user and directory_user.tenant_id else [])
            + [group.tenant_id for group in groups]
        ),
        directory_team_ids=_unique_non_empty(
            ([directory_user.team_id] if directory_user and directory_user.team_id else [])
            + [group.team_id for group in groups]
        ),
        directory_roles=_unique_non_empty([group.mapped_role for group in groups if group.mapped_role]),
        group_ids=tuple(group.group_id for group in groups),
    )
