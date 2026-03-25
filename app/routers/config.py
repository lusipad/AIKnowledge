from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import ConfigProfile, ConfigProfileVersion
from app.request_context import get_request_context
from app.security import require_min_role
from app.schemas import ConfigProfileUpsertRequest, ConfigRollbackRequest
from app.services.audit import append_audit_log
from app.services.isolation import apply_config_scope
from app.services.resource_acl import can_view_resource
from app.services.use_cases import AuthorizationError, InvalidOperationError, ResourceNotFoundError, ensure_profile_writable, upsert_profile_data
from app.services.vector_store import sync_config_vector_index
from app.utils import api_response


router = APIRouter(prefix="/api/v1", tags=["config"])


def _record_profile_version(database: Session, profile: ConfigProfile) -> None:
    database.add(
        ConfigProfileVersion(
            profile_id=profile.profile_id,
            tenant_id=profile.tenant_id,
            team_id=profile.team_id,
            version=profile.version,
            content=profile.content,
            acl=profile.acl,
            status=profile.status,
        )
    )


@router.get("/config/profile")
def get_profiles(
    scope_type: str | None = None,
    scope_id: str | None = None,
    profile_type: str | None = None,
    database: Session = Depends(get_db),
    _: str = Depends(require_min_role('viewer')),
):
    request_context = get_request_context()
    statement = apply_config_scope(select(ConfigProfile).order_by(ConfigProfile.updated_at.desc()))
    if scope_type:
        statement = statement.where(ConfigProfile.scope_type == scope_type)
    if scope_id:
        statement = statement.where(ConfigProfile.scope_id == scope_id)
    if profile_type:
        statement = statement.where(ConfigProfile.profile_type == profile_type)

    profiles = [
        profile for profile in database.scalars(statement).all() if can_view_resource(profile.acl, request_context)
    ]
    return api_response(
        [
            {
                "profile_id": profile.profile_id,
                "tenant_id": profile.tenant_id,
                "team_id": profile.team_id,
                "scope_type": profile.scope_type,
                "scope_id": profile.scope_id,
                "profile_type": profile.profile_type,
                "content": profile.content,
                "acl": profile.acl,
                "version": profile.version,
                "status": profile.status,
            }
            for profile in profiles
        ]
    )


@router.get("/config/profile/{profile_id}")
def get_profile(
    profile_id: str,
    database: Session = Depends(get_db),
    _: str = Depends(require_min_role('viewer')),
):
    request_context = get_request_context()
    profile = database.scalar(apply_config_scope(select(ConfigProfile).where(ConfigProfile.profile_id == profile_id)))
    if not profile or not can_view_resource(profile.acl, request_context):
        raise HTTPException(status_code=404, detail="profile not found")

    versions = database.scalars(
        select(ConfigProfileVersion).where(ConfigProfileVersion.profile_id == profile_id).order_by(ConfigProfileVersion.version.desc())
    ).all()
    return api_response(
        {
            "profile_id": profile.profile_id,
            "tenant_id": profile.tenant_id,
            "team_id": profile.team_id,
            "scope_type": profile.scope_type,
            "scope_id": profile.scope_id,
            "profile_type": profile.profile_type,
            "content": profile.content,
            "acl": profile.acl,
            "version": profile.version,
            "status": profile.status,
            "history": [
                {"version": version.version, "status": version.status, "created_at": version.created_at.isoformat()}
                for version in versions
            ],
        }
    )


@router.put("/config/profile/{profile_id}")
def upsert_profile(
    profile_id: str,
    payload: ConfigProfileUpsertRequest,
    database: Session = Depends(get_db),
    _: str = Depends(require_min_role('admin')),
):
    try:
        return api_response(upsert_profile_data(profile_id, payload, database))
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except InvalidOperationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/config/profile/{profile_id}/rollback")
def rollback_profile(
    profile_id: str,
    payload: ConfigRollbackRequest,
    database: Session = Depends(get_db),
    _: str = Depends(require_min_role('admin')),
):
    request_context = get_request_context()
    profile = database.scalar(apply_config_scope(select(ConfigProfile).where(ConfigProfile.profile_id == profile_id)))
    if not profile:
        raise HTTPException(status_code=404, detail="profile not found")
    try:
        ensure_profile_writable(profile, request_context)
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except InvalidOperationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    versions = database.scalars(
        select(ConfigProfileVersion).where(ConfigProfileVersion.profile_id == profile_id).order_by(ConfigProfileVersion.version.desc())
    ).all()
    if not versions:
        raise HTTPException(status_code=404, detail="profile history not found")

    target_version = None
    if payload.target_version is not None:
        for version in versions:
            if version.version == payload.target_version:
                target_version = version
                break
    else:
        for version in versions:
            if version.version < profile.version:
                target_version = version
                break

    if target_version is None:
        raise HTTPException(status_code=404, detail="target version not found")

    profile.content = target_version.content
    profile.acl = target_version.acl
    profile.status = target_version.status
    profile.version += 1
    _record_profile_version(database, profile)
    sync_config_vector_index(database, profile)
    append_audit_log(
        database,
        actor_id=request_context.user_id or payload.actor_id,
        action="config.rollback",
        resource_type="config",
        resource_id=profile.profile_id,
        scope_type=profile.scope_type,
        scope_id=profile.scope_id,
        detail={"restored_from": target_version.version, "new_version": profile.version},
    )
    database.commit()
    return api_response(
        {
            "profile_id": profile.profile_id,
            "tenant_id": profile.tenant_id,
            "team_id": profile.team_id,
            "version": profile.version,
            "restored_from": target_version.version,
            "status": profile.status,
        }
    )
