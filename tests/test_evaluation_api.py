import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.dependencies import get_db
from app.services.bootstrap import seed_default_profiles
from tests.support import build_test_app


class EvaluationApiTestCase(unittest.TestCase):
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

        self.app = build_test_app()
        self.app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(self.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_run_evaluation_and_fetch_history(self):
        headers = {
            'X-Request-Id': 'req_eval_001',
            'X-Tenant-Id': 'tenant-eval',
            'X-Team-Id': 'team-eval',
            'X-User-Id': 'user-eval',
            'X-Client-Type': 'console',
        }

        scenarios_response = self.client.get('/api/v1/evaluation/scenarios', headers=headers)
        self.assertEqual(scenarios_response.status_code, 200)
        self.assertEqual(scenarios_response.json()['data']['items'][0]['scenario_id'], 'order_risk_regression_zh')

        run_response = self.client.post(
            '/api/v1/evaluation/run',
            json={'scenario_id': 'order_risk_regression_zh', 'verify_llm': False, 'persist': True},
            headers=headers,
        )
        self.assertEqual(run_response.status_code, 200)
        run_payload = run_response.json()['data']
        self.assertEqual(run_payload['status'], 'ready')
        self.assertGreaterEqual(run_payload['score'], 90)
        self.assertEqual(run_payload['artifacts']['identity']['tenant_id'], 'tenant-eval')
        self.assertTrue(run_payload['artifacts']['knowledge_id'].startswith('kn_'))
        self.assertGreaterEqual(len(run_payload['artifacts']['knowledge_ids']), 1)
        self.assertIn('retrieval_generated_knowledge_prominent', [item['check_id'] for item in run_payload['checks']])
        self.assertIn('retrieval_summary_query_relevant', [item['check_id'] for item in run_payload['checks']])
        prominent_check = next(item for item in run_payload['checks'] if item['check_id'] == 'retrieval_generated_knowledge_prominent')
        self.assertTrue(prominent_check['passed'])

        history_response = self.client.get('/api/v1/evaluation/runs', headers=headers)
        self.assertEqual(history_response.status_code, 200)
        runs = history_response.json()['data']['items']
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]['run_id'], run_payload['run_id'])

        detail_response = self.client.get(f"/api/v1/evaluation/runs/{run_payload['run_id']}", headers=headers)
        self.assertEqual(detail_response.status_code, 200)
        detail_payload = detail_response.json()['data']
        self.assertEqual(detail_payload['scenario']['scenario_id'], 'order_risk_regression_zh')
        self.assertIn('audit_context_propagated', [item['check_id'] for item in detail_payload['checks']])

        foreign_headers = {
            'X-Request-Id': 'req_eval_002',
            'X-Tenant-Id': 'tenant-other',
            'X-Team-Id': 'team-other',
            'X-User-Id': 'user-other',
            'X-Client-Type': 'console',
        }
        foreign_history_response = self.client.get('/api/v1/evaluation/runs', headers=foreign_headers)
        self.assertEqual(foreign_history_response.status_code, 200)
        self.assertEqual(foreign_history_response.json()['data']['items'], [])

        foreign_detail_response = self.client.get(
            f"/api/v1/evaluation/runs/{run_payload['run_id']}",
            headers=foreign_headers,
        )
        self.assertEqual(foreign_detail_response.status_code, 404)


if __name__ == '__main__':
    unittest.main()
