import json
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import ConfigProfile, KnowledgeItem, VectorIndexEntry
from app.services.vector_store import (
    EmbeddingVectorBackend,
    PersistentPgVectorBackend,
    VectorDocument,
    build_config_vector_documents,
    create_vector_backend,
    sync_config_vector_index,
    sync_knowledge_vector_index,
)
from app.settings import AppSettings


class _FakeEmbeddingResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode('utf-8')

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _embedding_for_text(text: str) -> list[float]:
    normalized = text.lower()
    if '订单' in normalized or '风控' in normalized or '黑名单' in normalized:
        return [1.0, 0.0, 0.0]
    if '登录' in normalized or '界面' in normalized:
        return [0.0, 1.0, 0.0]
    return [0.0, 0.0, 1.0]


def _fake_urlopen(request, timeout):
    payload = json.loads(request.data.decode('utf-8'))
    inputs = payload['input']
    return _FakeEmbeddingResponse(
        {
            'data': [
                {'index': index, 'embedding': _embedding_for_text(text)}
                for index, text in enumerate(inputs)
            ]
        }
    )


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
        backend = create_vector_backend(settings=_build_settings(vector_backend='simple'))
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
        backend = EmbeddingVectorBackend(_build_settings(), urlopen=_fake_urlopen)
        matches = backend.score_documents(
            '订单风控规则',
            [
                VectorDocument(document_id='doc_1', text='订单风控规则必须通过统一规则引擎接入', metadata={}),
                VectorDocument(document_id='doc_2', text='用户登录界面样式调整', metadata={}),
            ],
        )
        self.assertEqual(matches[0].document_id, 'doc_1')
        self.assertGreater(matches[0].score, matches[1].score)


class PersistentVectorBackendTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            'sqlite://',
            connect_args={'check_same_thread': False},
            poolclass=StaticPool,
        )
        self.SessionTesting = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, expire_on_commit=False)
        Base.metadata.create_all(bind=self.engine)
        self.database = self.SessionTesting()
        self.settings = _build_settings(vector_backend='pgvector')

    def tearDown(self):
        self.database.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_pgvector_backend_persists_and_scores_knowledge_embeddings(self):
        backend = PersistentPgVectorBackend(self.settings, urlopen=_fake_urlopen)
        documents = [
            VectorDocument(
                document_id='kn_rule',
                text='订单风控规则必须通过统一规则引擎接入',
                metadata={'entity_type': 'knowledge', 'entity_id': 'kn_rule'},
            ),
            VectorDocument(
                document_id='kn_ui',
                text='用户登录界面样式调整',
                metadata={'entity_type': 'knowledge', 'entity_id': 'kn_ui'},
            ),
        ]

        matches = backend.score_documents('订单风控规则', documents, database=self.database)
        stored_entries = self.database.scalars(select(VectorIndexEntry).order_by(VectorIndexEntry.document_id)).all()

        self.assertEqual(matches[0].document_id, 'kn_rule')
        self.assertEqual(len(stored_entries), 2)
        self.assertEqual(stored_entries[0].embedding_model, 'text-embedding-3-small')

    def test_sync_helpers_persist_knowledge_and_config_vectors(self):
        knowledge = KnowledgeItem(
            knowledge_id='kn_blacklist_rule',
            tenant_id='tenant-demo',
            team_id='team-demo',
            scope_type='path',
            scope_id='src/order/risk',
            knowledge_type='rule',
            memory_type='semantic',
            title='渠道黑名单命中必须记录原因',
            content={
                'background': '订单风控新增渠道黑名单校验时，需要保留命中原因以便排查。',
                'conclusion': '新增渠道黑名单校验时，必须记录命中原因。',
                'summary': '订单风控知识',
                'tags': ['订单风控', '黑名单'],
            },
            status='active',
            quality_score=0.98,
            confidence_score=0.95,
            freshness_score=1.0,
            version=1,
            created_by='test-suite',
        )
        profile = ConfigProfile(
            profile_id='cfg_team_rule',
            scope_type='team',
            scope_id='team:tenant-demo:team-demo',
            profile_type='coding_rule',
            content={'instructions': ['团队级数据库变更必须走回滚预案。']},
            version=1,
            status='active',
        )
        self.database.add(knowledge)
        self.database.add(profile)
        self.database.flush()

        sync_knowledge_vector_index(self.database, knowledge, settings=self.settings, urlopen=_fake_urlopen)
        sync_config_vector_index(self.database, profile, settings=self.settings, urlopen=_fake_urlopen)

        entries = self.database.scalars(select(VectorIndexEntry).order_by(VectorIndexEntry.document_id)).all()
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].entity_type, 'config_profile')
        self.assertEqual(entries[1].entity_type, 'knowledge')

        profile_documents = build_config_vector_documents(profile)
        backend = create_vector_backend(settings=self.settings, urlopen=_fake_urlopen)
        matches = backend.score_documents('数据库变更回滚预案', profile_documents, database=self.database)
        self.assertEqual(matches[0].document_id, profile_documents[0].document_id)


if __name__ == '__main__':
    unittest.main()
