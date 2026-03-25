import os
import unittest

from starlette.requests import Request

from app.security import extract_api_key, is_exempt_path, resolve_request_role
from app.settings import load_settings


class SecurityTestCase(unittest.TestCase):
    def test_exempt_paths(self):
        self.assertTrue(is_exempt_path('/'))
        self.assertTrue(is_exempt_path('/healthz'))
        self.assertTrue(is_exempt_path('/readyz'))
        self.assertTrue(is_exempt_path('/console'))
        self.assertTrue(is_exempt_path('/static/console/main.js'))
        self.assertTrue(is_exempt_path('/docs'))
        self.assertFalse(is_exempt_path('/api/v1/sessions'))

    def test_extract_api_key_from_headers(self):
        request = Request(
            {
                'type': 'http',
                'headers': [(b'x-api-key', b'secret-key')],
                'method': 'GET',
                'path': '/api/v1/sessions',
            }
        )
        self.assertEqual(extract_api_key(request), 'secret-key')

    def test_extract_api_key_from_bearer(self):
        request = Request(
            {
                'type': 'http',
                'headers': [(b'authorization', b'Bearer secret-token')],
                'method': 'GET',
                'path': '/api/v1/sessions',
            }
        )
        self.assertEqual(extract_api_key(request), 'secret-token')

    def test_load_settings_defaults(self):
        settings = load_settings()
        self.assertIn(settings.vector_backend, {'simple', 'keyword', 'simple-keyword', 'embedding', 'pgvector', 'postgres'})
        self.assertIn(settings.extraction_mode, {'sync', 'async'})

    def test_load_settings_supports_multiple_api_keys(self):
        previous_api_key = os.environ.get('AICODING_API_KEY')
        previous_api_keys = os.environ.get('AICODING_API_KEYS')
        os.environ['AICODING_API_KEYS'] = 'alpha, beta ,gamma'
        try:
            settings = load_settings()
        finally:
            if previous_api_key is None:
                os.environ.pop('AICODING_API_KEY', None)
            else:
                os.environ['AICODING_API_KEY'] = previous_api_key
            if previous_api_keys is None:
                os.environ.pop('AICODING_API_KEYS', None)
            else:
                os.environ['AICODING_API_KEYS'] = previous_api_keys
        self.assertEqual(settings.configured_api_keys, ('alpha', 'beta', 'gamma'))

    def test_load_settings_supports_api_key_role_mapping(self):
        previous_role_mapping = os.environ.get('AICODING_API_KEY_ROLES')
        os.environ['AICODING_API_KEY_ROLES'] = 'alpha:viewer,beta:writer,gamma:admin'
        try:
            settings = load_settings()
        finally:
            if previous_role_mapping is None:
                os.environ.pop('AICODING_API_KEY_ROLES', None)
            else:
                os.environ['AICODING_API_KEY_ROLES'] = previous_role_mapping
        self.assertEqual(settings.api_key_roles, {'alpha': 'viewer', 'beta': 'writer', 'gamma': 'admin'})

    def test_resolve_request_role_prefers_authenticated_role(self):
        request = Request(
            {
                'type': 'http',
                'headers': [(b'x-user-role', b'admin')],
                'method': 'GET',
                'path': '/api/v1/sessions',
            }
        )
        request.state.authenticated_role = 'viewer'
        self.assertEqual(resolve_request_role(request, default_role='writer'), 'viewer')


if __name__ == '__main__':
    unittest.main()
