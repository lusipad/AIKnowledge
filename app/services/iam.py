from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

import jwt

from app.settings import ALLOWED_USER_ROLES, AppSettings, load_settings


ROLE_RANK = {
    'viewer': 10,
    'writer': 20,
    'reviewer': 30,
    'admin': 40,
}

_JWKS_CACHE: dict[str, dict] = {}


class IamAuthenticationError(ValueError):
    pass


@dataclass(frozen=True)
class AuthenticatedIdentity:
    source: str
    user_id: str | None
    user_role: str | None
    tenant_id: str | None
    team_id: str | None
    allowed_tenant_ids: tuple[str, ...]
    allowed_team_ids: tuple[str, ...]
    claims: dict


def _normalize_claim_values(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        values = [str(item).strip() for item in value if str(item).strip()]
        return list(dict.fromkeys(values))
    normalized = str(value).strip()
    return [normalized] if normalized else []


def _resolve_internal_role(raw_roles, settings: AppSettings) -> str | None:
    resolved_roles: list[str] = []
    for raw_role in _normalize_claim_values(raw_roles):
        mapped_role = settings.iam_role_mapping.get(raw_role, raw_role).lower()
        if mapped_role in ALLOWED_USER_ROLES:
            resolved_roles.append(mapped_role)
    if not resolved_roles:
        return None
    return max(resolved_roles, key=lambda item: ROLE_RANK.get(item, 0))


def _load_jwks(settings: AppSettings, *, urlopen=None) -> dict:
    if settings.iam_jwks_json:
        cache_key = f'inline::{settings.iam_jwks_json}'
        if cache_key not in _JWKS_CACHE:
            _JWKS_CACHE[cache_key] = json.loads(settings.iam_jwks_json)
        return _JWKS_CACHE[cache_key]
    if not settings.iam_jwks_url:
        raise IamAuthenticationError('IAM JWKS is not configured')

    cache_key = f'url::{settings.iam_jwks_url}'
    if cache_key in _JWKS_CACHE:
        return _JWKS_CACHE[cache_key]

    opener = urlopen or urllib.request.urlopen
    request = urllib.request.Request(
        settings.iam_jwks_url,
        headers={'Accept': 'application/json'},
        method='GET',
    )
    try:
        with opener(request, timeout=10) as response:
            payload = json.loads(response.read().decode('utf-8', 'replace'))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', 'replace')
        raise IamAuthenticationError(detail or str(exc)) from exc
    except urllib.error.URLError as exc:
        raise IamAuthenticationError(str(exc.reason)) from exc

    _JWKS_CACHE[cache_key] = payload
    return payload


def _select_jwk(token: str, settings: AppSettings, *, urlopen=None) -> tuple[dict, dict]:
    try:
        unverified_header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise IamAuthenticationError('invalid bearer token header') from exc

    jwks = _load_jwks(settings, urlopen=urlopen)
    keys = jwks.get('keys', [])
    if not isinstance(keys, list) or not keys:
        raise IamAuthenticationError('IAM JWKS does not contain any keys')

    kid = unverified_header.get('kid')
    for key in keys:
        if not kid or key.get('kid') == kid:
            return unverified_header, key
    raise IamAuthenticationError('matching IAM JWK key was not found')


def verify_bearer_token(
    token: str,
    *,
    settings: AppSettings | None = None,
    urlopen=None,
) -> AuthenticatedIdentity:
    current_settings = settings or load_settings()
    if not current_settings.iam_enabled:
        raise IamAuthenticationError('IAM authentication is not enabled')

    unverified_header, jwk = _select_jwk(token, current_settings, urlopen=urlopen)
    try:
        signing_key = jwt.PyJWK.from_dict(jwk).key
        claims = jwt.decode(
            token,
            key=signing_key,
            algorithms=[unverified_header.get('alg', 'RS256')],
            audience=current_settings.iam_audience or None,
            issuer=current_settings.iam_issuer or None,
            options={
                'verify_aud': bool(current_settings.iam_audience),
                'verify_iss': bool(current_settings.iam_issuer),
            },
        )
    except jwt.InvalidTokenError as exc:
        raise IamAuthenticationError(str(exc)) from exc

    user_id = str(claims.get(current_settings.iam_user_claim) or '').strip() or None
    if not user_id:
        raise IamAuthenticationError('IAM token does not contain a valid user identifier')
    allowed_tenant_ids = tuple(
        dict.fromkeys(
            _normalize_claim_values(claims.get(current_settings.iam_tenant_claim))
            + _normalize_claim_values(claims.get(current_settings.iam_tenants_claim))
        )
    )
    allowed_team_ids = tuple(
        dict.fromkeys(
            _normalize_claim_values(claims.get(current_settings.iam_team_claim))
            + _normalize_claim_values(claims.get(current_settings.iam_teams_claim))
        )
    )
    user_role = _resolve_internal_role(claims.get(current_settings.iam_role_claim), current_settings)
    if not user_role:
        raise IamAuthenticationError('IAM token does not contain a supported role')

    return AuthenticatedIdentity(
        source='iam',
        user_id=user_id,
        user_role=user_role,
        tenant_id=allowed_tenant_ids[0] if allowed_tenant_ids else None,
        team_id=allowed_team_ids[0] if allowed_team_ids else None,
        allowed_tenant_ids=allowed_tenant_ids,
        allowed_team_ids=allowed_team_ids,
        claims=claims,
    )


def synchronize_identity_scope(
    identity: AuthenticatedIdentity,
    *,
    requested_tenant_id: str | None,
    requested_team_id: str | None,
) -> AuthenticatedIdentity:
    active_tenant_id = identity.tenant_id
    if requested_tenant_id:
        if identity.allowed_tenant_ids and requested_tenant_id not in identity.allowed_tenant_ids:
            raise IamAuthenticationError('requested tenant is not granted by IAM token')
        active_tenant_id = requested_tenant_id
    elif not active_tenant_id and identity.allowed_tenant_ids:
        active_tenant_id = identity.allowed_tenant_ids[0]

    active_team_id = identity.team_id
    if requested_team_id:
        if identity.allowed_team_ids and requested_team_id not in identity.allowed_team_ids:
            raise IamAuthenticationError('requested team is not granted by IAM token')
        active_team_id = requested_team_id
    elif not active_team_id and identity.allowed_team_ids:
        active_team_id = identity.allowed_team_ids[0]

    return AuthenticatedIdentity(
        source=identity.source,
        user_id=identity.user_id,
        user_role=identity.user_role,
        tenant_id=active_tenant_id,
        team_id=active_team_id,
        allowed_tenant_ids=identity.allowed_tenant_ids,
        allowed_team_ids=identity.allowed_team_ids,
        claims=identity.claims,
    )
