import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.dependencies import get_db
from app.main import app
from app.models import ConfigProfile, ConversationSession, KnowledgeItem
from app.services.bootstrap import seed_default_profiles


class RetrievalQualityTestCase(unittest.TestCase):
    def setUp(self):
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
            database.add(
                ConversationSession(
                    session_id='sess_debug_001',
                    tenant_id=None,
                    team_id=None,
                    user_id='tester',
                    repo_id='demo-repo',
                    branch_name='feature/retrieval-quality',
                    task_id='TEST-RETRIEVAL-001',
                    client_type='test',
                    status='active',
                )
            )
            database.add(
                ConfigProfile(
                    profile_id='cfg_duplicate_rule',
                    scope_type='path',
                    scope_id='src/order/risk',
                    profile_type='coding_rule',
                    content={
                        'instructions': [
                            '所有业务规则变更都需要补充回归检查项。',
                            '订单风控路径下的实现必须补充回归检查清单，并在涉及黑名单校验时记录命中原因。',
                        ]
                    },
                    version=1,
                    status='active',
                )
            )
            database.add(
                KnowledgeItem(
                    knowledge_id='kn_blacklist_rule',
                    tenant_id=None,
                    scope_type='path',
                    scope_id='src/order/risk',
                    knowledge_type='rule',
                    memory_type='semantic',
                    title='渠道黑名单命中必须记录原因并补充回归检查',
                    content={
                        'background': '订单风控新增渠道黑名单校验时，需要保留命中原因以便排查。',
                        'conclusion': '新增渠道黑名单校验时，必须记录命中原因，并补充回归检查清单。',
                        'summary': '订单风控的渠道黑名单校验需要进入统一规则引擎，同时把命中原因和回归检查项沉淀为可复用知识。',
                        'tags': ['订单风控', '黑名单', '回归'],
                    },
                    status='active',
                    quality_score=0.98,
                    confidence_score=0.95,
                    freshness_score=1.0,
                    version=1,
                    created_by='test-suite',
                )
            )
            database.add(
                KnowledgeItem(
                    knowledge_id='kn_generic_rule',
                    tenant_id=None,
                    scope_type='repo',
                    scope_id='demo-repo',
                    knowledge_type='rule',
                    memory_type='semantic',
                    title='风控逻辑优先接入统一规则引擎',
                    content={
                        'background': '风控逻辑需要统一治理。',
                        'conclusion': '新增风控逻辑时优先复用统一规则引擎。',
                        'summary': '仓库级通用规则，强调统一规则引擎接入。',
                        'tags': ['订单风控', '规则引擎'],
                    },
                    status='active',
                    quality_score=0.82,
                    confidence_score=0.82,
                    freshness_score=1.0,
                    version=1,
                    created_by='test-suite',
                )
            )
            database.commit()
        finally:
            database.close()

        def override_get_db():
            database = self.SessionTesting()
            try:
                yield database
            finally:
                database.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_retrieval_prioritizes_generated_knowledge_and_bounds_config_noise(self):
        response = self.client.post(
            '/api/v1/retrieval/debug',
            json={
                'session_id': 'sess_debug_001',
                'query': '为订单风控增加渠道黑名单校验与回归检查',
                'query_type': 'feature_impl',
                'repo_id': 'demo-repo',
                'branch_name': 'feature/retrieval-quality',
                'file_paths': ['src/order/risk/check.ts'],
                'token_budget': 2200,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()['data']['context_pack']

        self.assertIn('渠道黑名单', payload['context_summary'])
        self.assertEqual(payload['sources'][0]['knowledge_id'], 'kn_blacklist_rule')
        self.assertEqual(payload['rules'][0]['source_type'], 'knowledge_item')

        config_sources = [item for item in payload['sources'] if item['source_type'] == 'config_profile']
        self.assertLessEqual(len(config_sources), 3)

        rule_titles = [item['title'] for item in payload['rules']]
        self.assertEqual(rule_titles.count('所有业务规则变更都需要补充回归检查项。'), 1)


if __name__ == '__main__':
    unittest.main()
