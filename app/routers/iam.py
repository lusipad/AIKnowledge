from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.request_context import get_request_context
from app.schemas import DirectoryGroupUpsertRequest, DirectorySyncRequest, DirectoryUserUpsertRequest
from app.security import require_min_role
from app.services.directory import (
    DirectoryAuthorizationError,
    DirectorySyncError,
    list_directory_groups,
    list_directory_users,
    serialize_directory_group,
    serialize_directory_user,
    sync_directory_snapshot,
    upsert_directory_group,
    upsert_directory_user,
)
from app.utils import api_response


router = APIRouter(prefix='/api/v1', tags=['iam'])


@router.get('/iam/directory/users')
def get_directory_users(
    database: Session = Depends(get_db),
    _: str = Depends(require_min_role('admin')),
):
    return api_response({'items': list_directory_users(database, get_request_context())})


@router.put('/iam/scim/users/{user_id}')
def put_directory_user(
    user_id: str,
    payload: DirectoryUserUpsertRequest,
    database: Session = Depends(get_db),
    _: str = Depends(require_min_role('admin')),
):
    try:
        directory_user = upsert_directory_user(database, user_id, payload, get_request_context())
        database.commit()
    except DirectoryAuthorizationError as exc:
        database.rollback()
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except DirectorySyncError as exc:
        database.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return api_response(serialize_directory_user(directory_user))


@router.get('/iam/directory/groups')
def get_directory_groups(
    database: Session = Depends(get_db),
    _: str = Depends(require_min_role('admin')),
):
    return api_response({'items': list_directory_groups(database, get_request_context())})


@router.put('/iam/scim/groups/{group_id}')
def put_directory_group(
    group_id: str,
    payload: DirectoryGroupUpsertRequest,
    database: Session = Depends(get_db),
    _: str = Depends(require_min_role('admin')),
):
    try:
        directory_group = upsert_directory_group(database, group_id, payload, get_request_context())
        database.commit()
    except DirectoryAuthorizationError as exc:
        database.rollback()
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except DirectorySyncError as exc:
        database.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return api_response(serialize_directory_group(database, directory_group))


@router.post('/iam/directory/sync')
def sync_directory(
    payload: DirectorySyncRequest,
    database: Session = Depends(get_db),
    _: str = Depends(require_min_role('admin')),
):
    try:
        return api_response(sync_directory_snapshot(database, payload, get_request_context()))
    except DirectoryAuthorizationError as exc:
        database.rollback()
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except DirectorySyncError as exc:
        database.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
