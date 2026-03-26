import json
import unittest
import urllib.error

from app.services.llm_validation import build_chat_completions_url, verify_llm_connection
from app.settings import AppSettings


class _FakeResponse:
    def __init__(self, payload: dict, status: int = 200):
        self._payload = payload
        self.status = status

    def read(self):
        return json.dumps(self._payload).encode('utf-8')

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeHttpError(urllib.error.HTTPError):
    def __init__(self, url: str, code: int, body: bytes):
        super().__init__(url=url, code=code, msg='Forbidden', hdrs=None, fp=None)
        self._body = body

    def read(self):
        return self._body


def _build_settings(**overrides) -> AppSettings:
    defaults = {
        'app_name': 'AI Coding Knowledge & Memory MVP',
        'app_version': '0.4.0',
        'db_url': 'sqlite:///:memory:',
        'vector_backend': 'simple',
        'extraction_mode': 'sync',
        'api_key': None,
        'env': 'test',
        'embedding_base_url': 'https://example.com',
        'embedding_api_key': 'secret',
        'embedding_model': 'text-embedding-3-small',
        'vector_dimensions': 1536,
        'embedding_path': '/v1/embeddings',
        'embedding_timeout_sec': 10,
        'llm_base_url': 'https://example.com',
        'llm_api_key': 'secret',
        'llm_model': 'gpt-5.4-low',
        'llm_chat_path': '/v1/chat/completions',
        'llm_timeout_sec': 10,
    }
    defaults.update(overrides)
    return AppSettings(**defaults)


class LlmValidationTestCase(unittest.TestCase):
    def test_build_chat_completions_url(self):
        settings = _build_settings()
        self.assertEqual(build_chat_completions_url(settings), 'https://example.com/v1/chat/completions')

    def test_verify_llm_connection_success(self):
        settings = _build_settings()

        def fake_urlopen(request, timeout):
            self.assertEqual(timeout, 10)
            self.assertEqual(request.full_url, 'https://example.com/v1/chat/completions')
            return _FakeResponse(
                {
                    'choices': [
                        {
                            'message': {
                                'content': 'ok',
                            }
                        }
                    ]
                }
            )

        result = verify_llm_connection(settings, urlopen=fake_urlopen)
        self.assertTrue(result.ok)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.response_text, 'ok')

    def test_verify_llm_connection_http_error(self):
        settings = _build_settings()

        def fake_urlopen(request, timeout):
            raise _FakeHttpError(request.full_url, 403, b'error code: 1010')

        result = verify_llm_connection(settings, urlopen=fake_urlopen)
        self.assertFalse(result.ok)
        self.assertEqual(result.status_code, 403)
        self.assertEqual(result.error, 'upstream_http_error')
        self.assertIn('1010', result.detail)

    def test_verify_llm_connection_requires_configuration(self):
        settings = _build_settings(llm_api_key=None)
        result = verify_llm_connection(settings)
        self.assertFalse(result.ok)
        self.assertFalse(result.configured)
        self.assertEqual(result.error, 'llm_not_configured')


if __name__ == '__main__':
    unittest.main()
