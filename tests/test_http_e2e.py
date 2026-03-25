import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.dependencies import get_db
from app.main import app
from app.services.bootstrap import seed_default_profiles


class HttpE2EFlowTestCase(unittest.TestCase):
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

    def test_http_end_to_end_flow(self):
        session_response = self.client.post(
            '/api/v1/sessions',
            json={
                'repo_id': 'demo-repo',
                'branch_name': 'feature/http-e2e',
                'task_id': 'ISSUE-2048',
                'client_type': 'cli',
            },
        )
        self.assertEqual(session_response.status_code, 200)
        session_id = session_response.json()['data']['session_id']

        events_response = self.client.post(
            '/api/v1/context/events',
            json={
                'session_id': session_id,
                'events': [
                    {
                        'event_type': 'prompt',
                        'summary': '订单风控规则必须通过统一规则引擎接入',
                        'file_paths': ['src/order/risk/check.ts'],
                        'symbol_names': [],
                    },
                    {
                        'event_type': 'test_result',
                        'summary': '修复后回归通过，形成回归案例',
                        'file_paths': ['src/order/risk/check.ts'],
                        'symbol_names': [],
                    },
                ],
            },
        )
        self.assertEqual(events_response.status_code, 200)
        signal_ids = events_response.json()['data']['created_signal_ids']
        self.assertEqual(len(signal_ids), 2)

        extract_response = self.client.post('/api/v1/knowledge/extract', json={'signal_ids': signal_ids, 'force': False})
        self.assertEqual(extract_response.status_code, 200)
        items = extract_response.json()['data']['items']
        self.assertEqual(len(items), 2)
        knowledge_id = items[0]['knowledge_id']
        self.assertFalse(items[0]['deduplicated'])

        extract_deduplicated_response = self.client.post('/api/v1/knowledge/extract', json={'signal_ids': signal_ids, 'force': False})
        self.assertEqual(extract_deduplicated_response.status_code, 200)
        self.assertTrue(extract_deduplicated_response.json()['data']['items'][0]['deduplicated'])

        review_response = self.client.post(
            '/api/v1/knowledge/review',
            json={'knowledge_id': knowledge_id, 'decision': 'approve', 'reviewer_id': 'reviewer-http'},
        )
        self.assertEqual(review_response.status_code, 200)
        self.assertEqual(review_response.json()['data']['status'], 'active')

        knowledge_list_response = self.client.get(
            '/api/v1/knowledge',
            params={'scope_type': 'path', 'scope_id': 'src/order/risk', 'keyword': 'demo-repo'},
        )
        self.assertEqual(knowledge_list_response.status_code, 200)
        self.assertGreaterEqual(knowledge_list_response.json()['data']['total'], 1)

        retrieval_response = self.client.post(
            '/api/v1/retrieval/query',
            json={
                'session_id': session_id,
                'query': '为订单风控增加渠道黑名单校验',
                'query_type': 'feature_impl',
                'repo_id': 'demo-repo',
                'branch_name': 'feature/http-e2e',
                'file_paths': ['src/order/risk/check.ts'],
                'token_budget': 2000,
            },
        )
        self.assertEqual(retrieval_response.status_code, 200)
        retrieval_payload = retrieval_response.json()
        self.assertIn('rules', retrieval_payload['data'])
        request_id = retrieval_payload['request_id']

        context_feedback_response = self.client.post(
            '/api/v1/feedback/context-pack',
            json={
                'request_id': request_id,
                'feedback_score': 4,
                'relevance_score': 5,
                'completeness_score': 4,
                'feedback_text': '帮助较大',
                'created_by': 'http-dev',
            },
        )
        self.assertEqual(context_feedback_response.status_code, 200)

        knowledge_feedback_response = self.client.post(
            '/api/v1/feedback/knowledge',
            json={
                'knowledge_id': knowledge_id,
                'request_id': request_id,
                'feedback_type': 'accepted',
                'feedback_score': 5,
                'feedback_text': '命中准确',
                'created_by': 'http-dev',
            },
        )
        self.assertEqual(knowledge_feedback_response.status_code, 200)

        audit_logs_response = self.client.get('/api/v1/audit/logs')
        self.assertEqual(audit_logs_response.status_code, 200)
        self.assertGreaterEqual(len(audit_logs_response.json()['data']), 1)


if __name__ == '__main__':
    unittest.main()
