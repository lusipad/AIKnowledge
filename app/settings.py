from __future__ import annotations

import os
from dataclasses import dataclass, field


ALLOWED_VECTOR_BACKENDS = {'simple', 'keyword', 'simple-keyword', 'embedding', 'pgvector', 'postgres'}
ALLOWED_EXTRACTION_MODES = {'sync', 'async'}
ALLOWED_USER_ROLES = {'viewer', 'writer', 'reviewer', 'admin'}


def _normalize_llm_chat_path(path: str | None) -> str:
    if not path:
        return '/v1/chat/completions'
    return path if path.startswith('/') else f'/{path}'


@dataclass(frozen=True)
class AppSettings:
    app_name: str
    app_version: str
    db_url: str
    vector_backend: str
    extraction_mode: str
    api_key: str | None
    env: str
    embedding_base_url: str | None
    embedding_api_key: str | None
    embedding_model: str | None
    vector_dimensions: int
    embedding_path: str
    embedding_timeout_sec: int
    llm_base_url: str | None
    llm_api_key: str | None
    llm_model: str | None
    llm_chat_path: str
    llm_timeout_sec: int
    default_user_role: str = 'admin'
    api_key_roles: dict[str, str] = field(default_factory=dict)
    iam_jwks_url: str | None = None
    iam_jwks_json: str | None = None
    iam_issuer: str | None = None
    iam_audience: str | None = None
    iam_user_claim: str = 'sub'
    iam_tenant_claim: str = 'tenant_id'
    iam_tenants_claim: str = 'tenant_ids'
    iam_team_claim: str = 'team_id'
    iam_teams_claim: str = 'team_ids'
    iam_role_claim: str = 'roles'
    iam_role_mapping: dict[str, str] = field(default_factory=dict)

    @property
    def api_key_enabled(self) -> bool:
        return bool(self.api_key)

    @property
    def iam_enabled(self) -> bool:
        return bool(self.iam_jwks_url or self.iam_jwks_json)

    @property
    def auth_enabled(self) -> bool:
        return self.api_key_enabled or self.iam_enabled

    @property
    def configured_api_keys(self) -> tuple[str, ...]:
        if not self.api_key:
            return ()
        keys = [item.strip() for item in self.api_key.split(',')]
        return tuple(dict.fromkeys([item for item in keys if item]))

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_base_url and self.llm_api_key and self.llm_model)

    @property
    def embedding_configured(self) -> bool:
        return bool(self.embedding_base_url and self.embedding_api_key and self.embedding_model)


def _parse_role_mapping(raw_value: str | None) -> dict[str, str]:
    if not raw_value:
        return {}
    mappings: dict[str, str] = {}
    for item in raw_value.split(','):
        if ':' not in item:
            continue
        key, role = item.split(':', 1)
        normalized_key = key.strip()
        normalized_role = role.strip().lower()
        if not normalized_key or normalized_role not in ALLOWED_USER_ROLES:
            continue
        mappings[normalized_key] = normalized_role
    return mappings



def load_settings() -> AppSettings:
    vector_backend = os.getenv('AICODING_VECTOR_BACKEND', 'simple').lower()
    if vector_backend not in ALLOWED_VECTOR_BACKENDS:
        raise ValueError(f'Unsupported vector backend: {vector_backend}')
    extraction_mode = os.getenv('AICODING_EXTRACTION_MODE', 'sync').lower()
    if extraction_mode not in ALLOWED_EXTRACTION_MODES:
        raise ValueError(f'Unsupported extraction mode: {extraction_mode}')

    default_user_role = os.getenv('AICODING_DEFAULT_USER_ROLE', 'admin').lower()
    if default_user_role not in ALLOWED_USER_ROLES:
        raise ValueError(f'Unsupported default user role: {default_user_role}')

    return AppSettings(
        app_name='AI Coding Knowledge & Memory MVP',
        app_version='0.7.0',
        db_url=os.getenv('AICODING_DB_URL', 'sqlite:///./aicoding_mvp.db'),
        vector_backend=vector_backend,
        extraction_mode=extraction_mode,
        api_key=(os.getenv('AICODING_API_KEYS') or os.getenv('AICODING_API_KEY') or '').strip() or None,
        default_user_role=default_user_role,
        api_key_roles=_parse_role_mapping(os.getenv('AICODING_API_KEY_ROLES')),
        env=os.getenv('AICODING_ENV', 'dev'),
        embedding_base_url=(os.getenv('AICODING_EMBEDDING_BASE_URL') or '').rstrip('/') or None,
        embedding_api_key=os.getenv('AICODING_EMBEDDING_API_KEY') or None,
        embedding_model=os.getenv('AICODING_EMBEDDING_MODEL') or None,
        vector_dimensions=max(1, int(os.getenv('AICODING_VECTOR_DIMENSIONS', '1536'))),
        embedding_path=_normalize_llm_chat_path(os.getenv('AICODING_EMBEDDING_PATH')).replace('/chat/completions', '/embeddings'),
        embedding_timeout_sec=max(1, int(os.getenv('AICODING_EMBEDDING_TIMEOUT_SEC', '30'))),
        llm_base_url=(os.getenv('AICODING_LLM_BASE_URL') or '').rstrip('/') or None,
        llm_api_key=os.getenv('AICODING_LLM_API_KEY') or None,
        llm_model=os.getenv('AICODING_LLM_MODEL') or None,
        llm_chat_path=_normalize_llm_chat_path(os.getenv('AICODING_LLM_CHAT_PATH')),
        llm_timeout_sec=max(1, int(os.getenv('AICODING_LLM_TIMEOUT_SEC', '30'))),
        iam_jwks_url=(os.getenv('AICODING_IAM_JWKS_URL') or '').strip() or None,
        iam_jwks_json=(os.getenv('AICODING_IAM_JWKS_JSON') or '').strip() or None,
        iam_issuer=(os.getenv('AICODING_IAM_ISSUER') or '').strip() or None,
        iam_audience=(os.getenv('AICODING_IAM_AUDIENCE') or '').strip() or None,
        iam_user_claim=(os.getenv('AICODING_IAM_USER_CLAIM') or 'sub').strip() or 'sub',
        iam_tenant_claim=(os.getenv('AICODING_IAM_TENANT_CLAIM') or 'tenant_id').strip() or 'tenant_id',
        iam_tenants_claim=(os.getenv('AICODING_IAM_TENANTS_CLAIM') or 'tenant_ids').strip() or 'tenant_ids',
        iam_team_claim=(os.getenv('AICODING_IAM_TEAM_CLAIM') or 'team_id').strip() or 'team_id',
        iam_teams_claim=(os.getenv('AICODING_IAM_TEAMS_CLAIM') or 'team_ids').strip() or 'team_ids',
        iam_role_claim=(os.getenv('AICODING_IAM_ROLE_CLAIM') or 'roles').strip() or 'roles',
        iam_role_mapping=_parse_role_mapping(os.getenv('AICODING_IAM_ROLE_MAPPING')),
    )
