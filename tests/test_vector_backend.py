import unittest

from app.services.vector_store import EmbeddingVectorBackend, SimpleKeywordVectorBackend, VectorDocument
from app.settings import AppSettings


class _FakeEmbeddingResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self):
        import json

        return json.dumps(self._payload).encode('utf-8')

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _build_settings(**overrides) -> AppSettings:
    defaults = {
        'app_name': 'AI Coding Knowledge & Memory MVP',
        'app_version': '0.7.0',
        'db_url': 'sqlite:///:memory:',
        'vector_backend': 'embedding',
        'extraction_mode': 'sync',
        'api_key': None,
        'env': 'test',
        'embedding_base_url': 'https://example.com',
        'embedding_api_key': 'secret',
        'embedding_model': 'text-embedding-3-small',
        'embedding_path': '/v1/embeddings',
        'embedding_timeout_sec': 10,
        'llm_base_url': None,
        'llm_api_key': None,
        'llm_model': None,
        'llm_chat_path': '/v1/chat/completions',
        'llm_timeout_sec': 10,
    }
    defaults.update(overrides)
    return AppSettings(**defaults)


class VectorBackendTestCase(unittest.TestCase):
    def test_simple_keyword_vector_scores_relevant_document_higher(self):
        backend = SimpleKeywordVectorBackend()
        matches = backend.score_documents(
            '订单风控规则',
            [
                VectorDocument(document_id='doc_1', text='订单风控规则必须通过统一规则引擎接入', metadata={}),
                VectorDocument(document_id='doc_2', text='用户登录界面样式调整', metadata={}),
            ],
        )
        self.assertEqual(matches[0].document_id, 'doc_1')
        self.assertGreater(matches[0].score, matches[1].score)

    def test_embedding_vector_scores_relevant_document_higher(self):
        def fake_urlopen(request, timeout):
            self.assertEqual(timeout, 10)
            self.assertEqual(request.full_url, 'https://example.com/v1/embeddings')
            return _FakeEmbeddingResponse(
                {
                    'data': [
                        {'index': 0, 'embedding': [1.0, 0.0, 0.0]},
                        {'index': 1, 'embedding': [0.9, 0.1, 0.0]},
                        {'index': 2, 'embedding': [0.0, 1.0, 0.0]},
                    ]
                }
            )

        backend = EmbeddingVectorBackend(_build_settings(), urlopen=fake_urlopen)
        matches = backend.score_documents(
            '订单风控规则',
            [
                VectorDocument(document_id='doc_1', text='订单风控规则必须通过统一规则引擎接入', metadata={}),
                VectorDocument(document_id='doc_2', text='用户登录界面样式调整', metadata={}),
            ],
        )
        self.assertEqual(matches[0].document_id, 'doc_1')
        self.assertGreater(matches[0].score, matches[1].score)


if __name__ == '__main__':
    unittest.main()
