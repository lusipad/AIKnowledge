import unittest

from starlette.requests import Request

from app.security import extract_api_key, is_exempt_path
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
        self.assertIn(settings.vector_backend, {'simple', 'keyword', 'simple-keyword', 'pgvector', 'postgres'})
        self.assertIn(settings.extraction_mode, {'sync', 'async'})


if __name__ == '__main__':
    unittest.main()
