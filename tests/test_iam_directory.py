import json
import os
import unittest
from contextlib import asynccontextmanager

import jwt
from fastapi import FastAPI
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.dependencies import get_db
from app.request_context import RequestContextMiddleware
from app.routers.auth import router as auth_router
from app.routers.iam import router as iam_router
from app.security import AuthenticationMiddleware
import app.services.iam as iam_module
from app.services.bootstrap import seed_default_profiles
from app.settings import load_settings


def _build_rsa_fixture():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk['kid'] = 'directory-test-key'
    return private_key, {'keys': [public_jwk]}


class IamDirectorySyncTestCase(unittest.TestCase):
    def setUp(self):
        self.previous_env = {key: os.environ.get(key) for key in (
            'AICODING_API_KEY',
            'AICODING_API_KEYS',
            'AICODING_IAM_JWKS_URL',
            'AICODING_IAM_JWKS_JSON',
            'AICODING_IAM_ISSUER',
            'AICODING_IAM_AUDIENCE',
            'AICODING_IAM_ROLE_MAPPING',
        )}
        private_key, jwks = _build_rsa_fixture()
        self.private_key = private_key
        os.environ.pop('AICODING_API_KEY', None)
        os.environ.pop('AICODING_API_KEYS', None)
        os.environ.pop('AICODING_IAM_JWKS_URL', None)
        os.environ['AICODING_IAM_JWKS_JSON'] = json.dumps(jwks)
        os.environ['AICODING_IAM_ISSUER'] = 'https://issuer.example'
        os.environ['AICODING_IAM_AUDIENCE'] = 'aiknowledge'
        os.environ['AICODING_IAM_ROLE_MAPPING'] = 'repo_viewer:viewer,repo_writer:writer,repo_reviewer:reviewer,repo_admin:admin'

        self.engine = create_engine(
            'sqlite://',
            connect_args={'check_same_thread': False},
            poolclass=StaticPool,
        )
        self.SessionTesting = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, expire_on_commit=False)
        Base.metadata.create_all(bind=self.engine)

        database = self.SessionTesting()
        try:
            seed_default_profiles(database)
            database.commit()
        finally:
            database.close()

        def override_get_db():
            database = self.SessionTesting()
            try:
                yield database
            finally:
                database.close()

        @asynccontextmanager
        async def lifespan(_: FastAPI):
            yield

        settings = load_settings()
        self.app = FastAPI(lifespan=lifespan)
        self.app.add_middleware(RequestContextMiddleware)
        self.app.add_middleware(
            AuthenticationMiddleware,
            api_keys=settings.configured_api_keys,
            api_key_roles=settings.api_key_roles,
            settings=settings,
        )
        self.app.include_router(auth_router)
        self.app.include_router(iam_router)
        self.app.dependency_overrides[get_db] = override_get_db
        self.previous_session_local = iam_module.SessionLocal
        iam_module.SessionLocal = self.SessionTesting
        self.client = TestClient(self.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        iam_module.SessionLocal = self.previous_session_local
        self.app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()
        for key, value in self.previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _build_token(self, *, roles, tenant_ids=None, team_ids=None, tenant_id=None, team_id=None, user_id='iam-user'):
        normalized_tenant_ids = tenant_ids or []
        normalized_team_ids = team_ids or []
        payload = {
            'iss': 'https://issuer.example',
            'aud': 'aiknowledge',
            'sub': user_id,
            'roles': roles,
        }
        if normalized_tenant_ids:
            payload['tenant_ids'] = normalized_tenant_ids
            payload['tenant_id'] = tenant_id or normalized_tenant_ids[0]
        if normalized_team_ids:
            payload['team_ids'] = normalized_team_ids
            payload['team_id'] = team_id or normalized_team_ids[0]
        return jwt.encode(
            payload,
            self.private_key,
            algorithm='RS256',
            headers={'kid': 'directory-test-key'},
        )

    def test_scim_upsert_and_list_directory_entities(self):
        admin_token = self._build_token(
            roles=['repo_admin'],
            tenant_ids=['tenant-dir'],
            team_ids=['team-dir'],
            user_id='directory-admin',
        )
        user_response = self.client.put(
            '/api/v1/iam/scim/users/user-directory',
            json={
                'email': 'user-directory@example.com',
                'display_name': 'Directory User',
                'attributes': {'department': 'platform'},
            },
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        self.assertEqual(user_response.status_code, 200)
        self.assertEqual(user_response.json()['data']['tenant_id'], 'tenant-dir')
        self.assertEqual(user_response.json()['data']['team_id'], 'team-dir')

        group_response = self.client.put(
            '/api/v1/iam/scim/groups/group-platform-reviewers',
            json={
                'display_name': 'Platform Reviewers',
                'scope_type': 'team',
                'mapped_role': 'reviewer',
                'member_user_ids': ['user-directory'],
                'attributes': {'source': 'scim'},
            },
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        self.assertEqual(group_response.status_code, 200)
        self.assertEqual(group_response.json()['data']['member_user_ids'], ['user-directory'])

        users_response = self.client.get(
            '/api/v1/iam/directory/users',
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        self.assertEqual(users_response.status_code, 200)
        self.assertEqual(users_response.json()['data']['items'][0]['email'], 'user-directory@example.com')

        groups_response = self.client.get(
            '/api/v1/iam/directory/groups',
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        self.assertEqual(groups_response.status_code, 200)
        self.assertEqual(groups_response.json()['data']['items'][0]['mapped_role'], 'reviewer')

    def test_directory_sync_augments_bearer_scope_and_role(self):
        admin_token = self._build_token(
            roles=['repo_admin'],
            tenant_ids=['tenant-sync'],
            team_ids=['team-sync'],
            user_id='directory-admin',
        )
        sync_response = self.client.post(
            '/api/v1/iam/directory/sync',
            json={
                'users': {
                    'scim-user': {
                        'display_name': 'SCIM Synced User',
                    }
                },
                'groups': {
                    'group-sync-admins': {
                        'display_name': 'Sync Admins',
                        'scope_type': 'team',
                        'mapped_role': 'admin',
                        'member_user_ids': ['scim-user'],
                    }
                },
            },
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        self.assertEqual(sync_response.status_code, 200)
        self.assertEqual(sync_response.json()['data']['group_count'], 1)

        viewer_token = self._build_token(roles=['repo_viewer'], user_id='scim-user')
        identity_response = self.client.get(
            '/api/v1/auth/identity',
            headers={'Authorization': f'Bearer {viewer_token}'},
        )
        self.assertEqual(identity_response.status_code, 200)
        payload = identity_response.json()['data']
        self.assertEqual(payload['user_role'], 'admin')
        self.assertEqual(payload['tenant_id'], 'tenant-sync')
        self.assertEqual(payload['team_id'], 'team-sync')
        self.assertEqual(payload['allowed_tenant_ids'], ['tenant-sync'])
        self.assertEqual(payload['allowed_team_ids'], ['team-sync'])
        self.assertEqual(payload['directory_group_ids'], ['group-sync-admins'])

    def test_directory_endpoints_require_admin_role(self):
        viewer_token = self._build_token(
            roles=['repo_viewer'],
            tenant_ids=['tenant-dir'],
            team_ids=['team-dir'],
            user_id='viewer-user',
        )
        blocked_response = self.client.post(
            '/api/v1/iam/directory/sync',
            json={
                'users': {'user-a': {'display_name': 'User A'}},
                'groups': {},
            },
            headers={'Authorization': f'Bearer {viewer_token}'},
        )
        self.assertEqual(blocked_response.status_code, 403)


if __name__ == '__main__':
    unittest.main()
