import json
import os
import unittest
from importlib import reload

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

import app.main as main_module


def _build_rsa_fixture():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk['kid'] = 'test-key'
    return private_key, {'keys': [public_jwk]}


class IamAuthTestCase(unittest.TestCase):
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
        self.main_module = reload(main_module)
        self.client = TestClient(self.main_module.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        for key, value in self.previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        reload(main_module)

    def _build_token(self, *, roles, tenant_ids, team_ids, tenant_id=None, team_id=None, user_id='iam-user'):
        return jwt.encode(
            {
                'iss': 'https://issuer.example',
                'aud': 'aiknowledge',
                'sub': user_id,
                'roles': roles,
                'tenant_ids': tenant_ids,
                'team_ids': team_ids,
                'tenant_id': tenant_id or tenant_ids[0],
                'team_id': team_id or team_ids[0],
            },
            self.private_key,
            algorithm='RS256',
            headers={'kid': 'test-key'},
        )

    def test_iam_identity_endpoint_uses_token_claims(self):
        token = self._build_token(
            roles=['repo_writer'],
            tenant_ids=['tenant-iam', 'tenant-alt'],
            team_ids=['team-iam', 'team-alt'],
        )
        response = self.client.get(
            '/api/v1/auth/identity',
            headers={'Authorization': f'Bearer {token}'},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()['data']
        self.assertEqual(payload['source'], 'iam')
        self.assertEqual(payload['user_id'], 'iam-user')
        self.assertEqual(payload['user_role'], 'writer')
        self.assertEqual(payload['tenant_id'], 'tenant-iam')
        self.assertEqual(payload['team_id'], 'team-iam')
        self.assertEqual(payload['allowed_tenant_ids'], ['tenant-iam', 'tenant-alt'])
        self.assertEqual(payload['allowed_team_ids'], ['team-iam', 'team-alt'])

    def test_iam_scope_override_accepts_granted_org_and_team(self):
        token = self._build_token(
            roles=['repo_writer'],
            tenant_ids=['tenant-iam', 'tenant-alt'],
            team_ids=['team-iam', 'team-alt'],
        )
        response = self.client.get(
            '/api/v1/auth/identity',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant-Id': 'tenant-alt',
                'X-Team-Id': 'team-alt',
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()['data']
        self.assertEqual(payload['tenant_id'], 'tenant-alt')
        self.assertEqual(payload['team_id'], 'team-alt')

    def test_iam_scope_override_rejects_ungranted_team(self):
        token = self._build_token(
            roles=['repo_writer'],
            tenant_ids=['tenant-iam'],
            team_ids=['team-iam'],
        )
        response = self.client.get(
            '/api/v1/auth/identity',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Team-Id': 'team-forbidden',
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_iam_role_mapping_controls_write_endpoint(self):
        viewer_token = self._build_token(
            roles=['repo_viewer'],
            tenant_ids=['tenant-iam'],
            team_ids=['team-iam'],
            user_id='viewer-user',
        )
        blocked_response = self.client.post(
            '/api/v1/sessions',
            json={
                'repo_id': 'demo-repo',
                'branch_name': 'feature/iam',
                'task_id': 'IAM-1',
                'client_type': 'cli',
            },
            headers={'Authorization': f'Bearer {viewer_token}'},
        )
        self.assertEqual(blocked_response.status_code, 403)

        writer_token = self._build_token(
            roles=['repo_writer'],
            tenant_ids=['tenant-iam'],
            team_ids=['team-iam'],
            user_id='writer-user',
        )
        allowed_response = self.client.post(
            '/api/v1/sessions',
            json={
                'repo_id': 'demo-repo',
                'branch_name': 'feature/iam',
                'task_id': 'IAM-2',
                'client_type': 'cli',
            },
            headers={'Authorization': f'Bearer {writer_token}'},
        )
        self.assertEqual(allowed_response.status_code, 200)
        session_payload = allowed_response.json()['data']
        self.assertEqual(session_payload['tenant_id'], 'tenant-iam')
        self.assertEqual(session_payload['team_id'], 'team-iam')
        self.assertEqual(session_payload['user_id'], 'writer-user')


if __name__ == '__main__':
    unittest.main()
