import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.dependencies import get_db
from app.services.bootstrap import seed_default_profiles
from tests.support import build_test_app


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

        self.app = build_test_app()
        self.app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(self.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_http_end_to_end_flow(self):
        request_headers = {
            'X-Request-Id': 'req_http_e2e_001',
            'X-Tenant-Id': 'tenant-demo',
            'X-Team-Id': 'team-demo',
            'X-User-Id': 'user-demo',
            'X-Client-Type': 'agent',
        }
        session_response = self.client.post(
            '/api/v1/sessions',
            json={
                'repo_id': 'demo-repo',
                'branch_name': 'feature/http-e2e',
                'task_id': 'ISSUE-2048',
                'client_type': 'cli',
            },
            headers=request_headers,
        )
        self.assertEqual(session_response.status_code, 200)
        self.assertEqual(session_response.headers['X-Request-Id'], 'req_http_e2e_001')
        session_payload = session_response.json()
        self.assertEqual(session_payload['request_id'], 'req_http_e2e_001')
        self.assertEqual(session_payload['data']['tenant_id'], 'tenant-demo')
        self.assertEqual(session_payload['data']['team_id'], 'team-demo')
        self.assertEqual(session_payload['data']['user_id'], 'user-demo')
        self.assertEqual(session_payload['data']['client_type'], 'agent')
        session_id = session_payload['data']['session_id']

        sessions_response = self.client.get(
            '/api/v1/sessions',
            params={'repo_id': 'demo-repo', 'page': 1, 'page_size': 10},
            headers=request_headers,
        )
        self.assertEqual(sessions_response.status_code, 200)
        self.assertEqual(sessions_response.json()['data']['total'], 1)
        self.assertEqual(sessions_response.json()['data']['items'][0]['session_id'], session_id)

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
            headers=request_headers,
        )
        self.assertEqual(events_response.status_code, 200)
        signal_ids = events_response.json()['data']['created_signal_ids']
        self.assertEqual(len(signal_ids), 2)

        extract_response = self.client.post(
            '/api/v1/knowledge/extract',
            json={'signal_ids': signal_ids, 'force': False},
            headers=request_headers,
        )
        self.assertEqual(extract_response.status_code, 200)
        items = extract_response.json()['data']['items']
        self.assertEqual(len(items), 2)
        knowledge_id = items[0]['knowledge_id']
        extract_task_id = items[0]['task_id']
        self.assertFalse(items[0]['deduplicated'])

        extract_deduplicated_response = self.client.post(
            '/api/v1/knowledge/extract',
            json={'signal_ids': signal_ids, 'force': False},
            headers=request_headers,
        )
        self.assertEqual(extract_deduplicated_response.status_code, 200)
        self.assertTrue(extract_deduplicated_response.json()['data']['items'][0]['deduplicated'])

        review_response = self.client.post(
            '/api/v1/knowledge/review',
            json={'knowledge_id': knowledge_id, 'decision': 'approve', 'reviewer_id': 'reviewer-http'},
            headers=request_headers,
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
            headers=request_headers,
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
            headers=request_headers,
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
            headers=request_headers,
        )
        self.assertEqual(knowledge_feedback_response.status_code, 200)

        invalidation_response = self.client.post(
            '/api/v1/context/events',
            json={
                'session_id': session_id,
                'events': [
                    {
                        'event_type': 'deploy',
                        'summary': '订单风控统一规则引擎已迁移到新服务，旧接入方式下线并被替换。',
                        'file_paths': ['src/order/risk/check.ts'],
                        'symbol_names': [],
                    }
                ],
            },
            headers=request_headers,
        )
        self.assertEqual(invalidation_response.status_code, 200)
        self.assertEqual(invalidation_response.json()['data']['freshness_updates'][0]['knowledge_id'], knowledge_id)
        self.assertEqual(invalidation_response.json()['data']['freshness_updates'][0]['status'], 'deprecated')

        retrieval_logs_response = self.client.get(
            '/api/v1/retrieval/logs',
            params={'session_id': session_id, 'repo_id': 'demo-repo', 'query_type': 'feature_impl', 'limit': 5},
            headers=request_headers,
        )
        self.assertEqual(retrieval_logs_response.status_code, 200)
        retrieval_logs_payload = retrieval_logs_response.json()['data']
        self.assertEqual(len(retrieval_logs_payload), 1)
        self.assertEqual(retrieval_logs_payload[0]['request_id'], request_id)
        self.assertEqual(retrieval_logs_payload[0]['knowledge_feedback_count'], 1)
        self.assertEqual(retrieval_logs_payload[0]['context_feedback']['feedback_score'], 4)

        retrieval_log_detail_response = self.client.get(
            f'/api/v1/retrieval/logs/{request_id}',
            headers=request_headers,
        )
        self.assertEqual(retrieval_log_detail_response.status_code, 200)
        retrieval_log_detail = retrieval_log_detail_response.json()['data']
        self.assertEqual(retrieval_log_detail['request_id'], request_id)
        self.assertEqual(len(retrieval_log_detail['context_pack_feedback']), 1)
        self.assertEqual(len(retrieval_log_detail['knowledge_feedback']), 1)

        audit_logs_response = self.client.get('/api/v1/audit/logs', headers=request_headers)
        self.assertEqual(audit_logs_response.status_code, 200)
        self.assertGreaterEqual(len(audit_logs_response.json()['data']), 1)
        self.assertEqual(audit_logs_response.json()['request_id'], 'req_http_e2e_001')
        self.assertEqual(audit_logs_response.json()['data'][0]['detail']['tenant_id'], 'tenant-demo')

        team_profile_id = 'cfg_team_demo'
        team_profile_response = self.client.put(
            f'/api/v1/config/profile/{team_profile_id}',
            json={
                'scope_type': 'team',
                'scope_id': 'team:tenant-demo:team-demo',
                'profile_type': 'prompt',
                'content': {'instructions': ['团队级数据库变更必须走回滚预案。']},
                'acl': {
                    'owners': ['user-demo'],
                    'editors': [],
                    'reviewers': [],
                    'viewers': ['user-demo'],
                },
                'version': 1,
                'status': 'active',
            },
            headers=request_headers,
        )
        self.assertEqual(team_profile_response.status_code, 200)
        self.assertEqual(team_profile_response.json()['data']['tenant_id'], 'tenant-demo')
        self.assertEqual(team_profile_response.json()['data']['team_id'], 'team-demo')

        team_repo_profile_id = 'cfg_repo_team_demo'
        team_repo_profile_response = self.client.put(
            f'/api/v1/config/profile/{team_repo_profile_id}',
            json={
                'scope_type': 'repo',
                'scope_id': 'demo-repo',
                'profile_type': 'prompt',
                'ownership_mode': 'team',
                'content': {'instructions': ['团队私有 repo 规则：支付链路变更必须补充灰度开关。']},
                'version': 1,
                'status': 'active',
            },
            headers=request_headers,
        )
        self.assertEqual(team_repo_profile_response.status_code, 200)
        self.assertEqual(team_repo_profile_response.json()['data']['tenant_id'], 'tenant-demo')
        self.assertEqual(team_repo_profile_response.json()['data']['team_id'], 'team-demo')
        self.assertEqual(team_repo_profile_response.json()['data']['ownership_mode'], 'team')

        tenant_admin_headers = {
            'X-Request-Id': 'req_http_e2e_005',
            'X-Tenant-Id': 'tenant-demo',
            'X-User-Id': 'tenant-admin',
            'X-User-Role': 'admin',
            'X-Client-Type': 'agent',
        }
        tenant_repo_profile_id = 'cfg_repo_tenant_demo'
        tenant_repo_profile_response = self.client.put(
            f'/api/v1/config/profile/{tenant_repo_profile_id}',
            json={
                'scope_type': 'repo',
                'scope_id': 'demo-repo',
                'profile_type': 'prompt',
                'ownership_mode': 'tenant',
                'content': {'instructions': ['租户私有 repo 规则：订单链路发布前必须核对租户开关矩阵。']},
                'version': 1,
                'status': 'active',
            },
            headers=tenant_admin_headers,
        )
        self.assertEqual(tenant_repo_profile_response.status_code, 200)
        self.assertEqual(tenant_repo_profile_response.json()['data']['tenant_id'], 'tenant-demo')
        self.assertIsNone(tenant_repo_profile_response.json()['data']['team_id'])
        self.assertEqual(tenant_repo_profile_response.json()['data']['ownership_mode'], 'tenant')

        migrate_team_repo_to_tenant = self.client.put(
            f'/api/v1/config/profile/{team_repo_profile_id}',
            json={
                'scope_type': 'repo',
                'scope_id': 'demo-repo',
                'profile_type': 'prompt',
                'ownership_mode': 'tenant',
                'content': {'instructions': ['团队 repo 规则已收敛为租户级共享规则。']},
                'version': 2,
                'status': 'active',
            },
            headers=request_headers,
        )
        self.assertEqual(migrate_team_repo_to_tenant.status_code, 200)
        self.assertIsNone(migrate_team_repo_to_tenant.json()['data']['team_id'])
        self.assertEqual(migrate_team_repo_to_tenant.json()['data']['ownership_mode'], 'tenant')

        shared_repo_profiles = self.client.get(
            '/api/v1/config/profile',
            params={'scope_type': 'repo', 'scope_id': 'demo-repo'},
            headers=request_headers,
        )
        self.assertEqual(shared_repo_profiles.status_code, 200)
        self.assertTrue(
            any(
                item['tenant_id'] is None and item['scope_type'] == 'repo' and item['scope_id'] == 'demo-repo'
                for item in shared_repo_profiles.json()['data']
            )
        )

        own_team_profile = self.client.get(
            f'/api/v1/config/profile/{team_profile_id}',
            headers=request_headers,
        )
        self.assertEqual(own_team_profile.status_code, 200)

        own_team_repo_profile = self.client.get(
            f'/api/v1/config/profile/{team_repo_profile_id}',
            headers=request_headers,
        )
        self.assertEqual(own_team_repo_profile.status_code, 200)
        self.assertEqual(own_team_repo_profile.json()['data']['team_id'], None)

        own_tenant_repo_profile = self.client.get(
            f'/api/v1/config/profile/{tenant_repo_profile_id}',
            headers=request_headers,
        )
        self.assertEqual(own_tenant_repo_profile.status_code, 200)

        lock_knowledge_acl = self.client.patch(
            f'/api/v1/knowledge/{knowledge_id}',
            json={
                'acl': {
                    'owners': ['user-demo'],
                    'editors': [],
                    'reviewers': ['reviewer-http', 'role:reviewer'],
                    'viewers': ['user-demo'],
                }
            },
            headers=request_headers,
        )
        self.assertEqual(lock_knowledge_acl.status_code, 200)

        viewer_headers = dict(request_headers)
        viewer_headers['X-User-Role'] = 'viewer'
        viewer_knowledge = self.client.get(f'/api/v1/knowledge/{knowledge_id}', headers=viewer_headers)
        self.assertEqual(viewer_knowledge.status_code, 200)

        viewer_profile_write = self.client.put(
            '/api/v1/config/profile/cfg_viewer_blocked',
            json={
                'scope_type': 'team',
                'scope_id': 'team:tenant-demo:team-demo',
                'profile_type': 'prompt',
                'content': {'instructions': ['viewer should not write config']},
                'version': 1,
                'status': 'active',
            },
            headers=viewer_headers,
        )
        self.assertEqual(viewer_profile_write.status_code, 403)

        viewer_knowledge_update = self.client.patch(
            f'/api/v1/knowledge/{knowledge_id}',
            json={'title': 'viewer should not update'},
            headers=viewer_headers,
        )
        self.assertEqual(viewer_knowledge_update.status_code, 403)

        viewer_evaluation_run = self.client.post(
            '/api/v1/evaluation/run',
            json={'scenario_id': 'order_risk_regression_zh', 'verify_llm': False, 'persist': False},
            headers=viewer_headers,
        )
        self.assertEqual(viewer_evaluation_run.status_code, 403)

        same_team_peer_headers = {
            'X-Request-Id': 'req_http_e2e_004',
            'X-Tenant-Id': 'tenant-demo',
            'X-Team-Id': 'team-demo',
            'X-User-Id': 'user-peer',
            'X-User-Role': 'writer',
            'X-Client-Type': 'agent',
        }
        same_team_peer_knowledge = self.client.get(
            f'/api/v1/knowledge/{knowledge_id}',
            headers=same_team_peer_headers,
        )
        self.assertEqual(same_team_peer_knowledge.status_code, 404)

        same_team_peer_update = self.client.patch(
            f'/api/v1/knowledge/{knowledge_id}',
            json={'title': 'peer should be blocked'},
            headers={**same_team_peer_headers, 'X-User-Role': 'admin'},
        )
        self.assertEqual(same_team_peer_update.status_code, 403)

        same_team_peer_profile = self.client.get(
            f'/api/v1/config/profile/{team_profile_id}',
            headers=same_team_peer_headers,
        )
        self.assertEqual(same_team_peer_profile.status_code, 404)

        same_team_peer_repo_profile = self.client.get(
            f'/api/v1/config/profile/{team_repo_profile_id}',
            headers=same_team_peer_headers,
        )
        self.assertEqual(same_team_peer_repo_profile.status_code, 200)

        lock_team_repo_profile = self.client.put(
            f'/api/v1/config/profile/{team_repo_profile_id}',
            json={
                'scope_type': 'repo',
                'scope_id': 'demo-repo',
                'profile_type': 'prompt',
                'content': {'instructions': ['团队私有 repo 规则：仅 owner 可见。']},
                'acl': {
                    'owners': ['user-demo'],
                    'editors': [],
                    'reviewers': [],
                    'viewers': ['user-demo'],
                },
                'version': 2,
                'status': 'active',
            },
            headers=request_headers,
        )
        self.assertEqual(lock_team_repo_profile.status_code, 200)

        same_team_peer_locked_repo_profile = self.client.get(
            f'/api/v1/config/profile/{team_repo_profile_id}',
            headers=same_team_peer_headers,
        )
        self.assertEqual(same_team_peer_locked_repo_profile.status_code, 404)

        rollback_team_repo_profile = self.client.post(
            f'/api/v1/config/profile/{team_repo_profile_id}/rollback',
            json={'target_version': 1, 'actor_id': 'user-demo'},
            headers=request_headers,
        )
        self.assertEqual(rollback_team_repo_profile.status_code, 200)
        self.assertEqual(rollback_team_repo_profile.json()['data']['restored_from'], 1)

        same_team_peer_repo_profile_after_rollback = self.client.get(
            f'/api/v1/config/profile/{team_repo_profile_id}',
            headers=same_team_peer_headers,
        )
        self.assertEqual(same_team_peer_repo_profile_after_rollback.status_code, 200)
        self.assertEqual(same_team_peer_repo_profile_after_rollback.json()['data']['ownership_mode'], 'team')

        same_team_peer_profile_update = self.client.put(
            f'/api/v1/config/profile/{team_profile_id}',
            json={
                'scope_type': 'team',
                'scope_id': 'team:tenant-demo:team-demo',
                'profile_type': 'prompt',
                'content': {'instructions': ['peer should be blocked']},
                'version': 2,
                'status': 'active',
            },
            headers={**same_team_peer_headers, 'X-User-Role': 'admin'},
        )
        self.assertEqual(same_team_peer_profile_update.status_code, 403)

        same_team_peer_retrieval = self.client.post(
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
            headers=same_team_peer_headers,
        )
        self.assertEqual(same_team_peer_retrieval.status_code, 200)
        self.assertFalse(
            any(item['knowledge_id'] == knowledge_id for item in same_team_peer_retrieval.json()['data']['sources'])
        )

        same_tenant_other_team_headers = {
            'X-Request-Id': 'req_http_e2e_003',
            'X-Tenant-Id': 'tenant-demo',
            'X-Team-Id': 'team-other',
            'X-User-Id': 'user-team-other',
            'X-Client-Type': 'agent',
        }
        same_tenant_other_team_knowledge = self.client.get(
            f'/api/v1/knowledge/{knowledge_id}',
            headers=same_tenant_other_team_headers,
        )
        self.assertEqual(same_tenant_other_team_knowledge.status_code, 404)

        same_tenant_other_team_extract = self.client.get(
            f'/api/v1/knowledge/extract/{extract_task_id}',
            headers=same_tenant_other_team_headers,
        )
        self.assertEqual(same_tenant_other_team_extract.status_code, 404)

        same_tenant_other_team_retrieval = self.client.post(
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
            headers=same_tenant_other_team_headers,
        )
        self.assertEqual(same_tenant_other_team_retrieval.status_code, 404)

        same_tenant_other_team_profile = self.client.get(
            f'/api/v1/config/profile/{team_profile_id}',
            headers=same_tenant_other_team_headers,
        )
        self.assertEqual(same_tenant_other_team_profile.status_code, 404)

        same_tenant_other_team_repo_profile = self.client.get(
            f'/api/v1/config/profile/{team_repo_profile_id}',
            headers=same_tenant_other_team_headers,
        )
        self.assertEqual(same_tenant_other_team_repo_profile.status_code, 404)

        same_tenant_other_team_tenant_repo_profile = self.client.get(
            f'/api/v1/config/profile/{tenant_repo_profile_id}',
            headers=same_tenant_other_team_headers,
        )
        self.assertEqual(same_tenant_other_team_tenant_repo_profile.status_code, 200)

        same_tenant_other_team_debug = self.client.post(
            '/api/v1/retrieval/debug',
            json={
                'session_id': session_id,
                'query': '为订单风控增加渠道黑名单校验',
                'query_type': 'feature_impl',
                'repo_id': 'demo-repo',
                'branch_name': 'feature/http-e2e',
                'file_paths': ['src/order/risk/check.ts'],
                'token_budget': 2000,
            },
            headers=same_tenant_other_team_headers,
        )
        self.assertEqual(same_tenant_other_team_debug.status_code, 404)

        foreign_headers = {
            'X-Request-Id': 'req_http_e2e_002',
            'X-Tenant-Id': 'tenant-other',
            'X-Team-Id': 'team-other',
            'X-User-Id': 'user-other',
            'X-Client-Type': 'agent',
        }
        foreign_sessions = self.client.get(
            '/api/v1/sessions',
            params={'repo_id': 'demo-repo', 'page': 1, 'page_size': 10},
            headers=foreign_headers,
        )
        self.assertEqual(foreign_sessions.status_code, 200)
        self.assertEqual(foreign_sessions.json()['data']['total'], 0)

        foreign_retrieval_log = self.client.get(
            f'/api/v1/retrieval/logs/{request_id}',
            headers=foreign_headers,
        )
        self.assertEqual(foreign_retrieval_log.status_code, 404)

        foreign_extract_task = self.client.get(
            f'/api/v1/knowledge/extract/{extract_task_id}',
            headers=foreign_headers,
        )
        self.assertEqual(foreign_extract_task.status_code, 404)

        foreign_knowledge_feedback = self.client.post(
            '/api/v1/feedback/knowledge',
            json={
                'knowledge_id': knowledge_id,
                'request_id': request_id,
                'feedback_type': 'accepted',
                'feedback_score': 5,
                'feedback_text': 'should be blocked',
                'created_by': 'user-other',
            },
            headers=foreign_headers,
        )
        self.assertEqual(foreign_knowledge_feedback.status_code, 404)

        foreign_audit_logs = self.client.get('/api/v1/audit/logs', headers=foreign_headers)
        self.assertEqual(foreign_audit_logs.status_code, 200)
        self.assertEqual(len(foreign_audit_logs.json()['data']), 0)

        foreign_profile = self.client.get(
            f'/api/v1/config/profile/{team_profile_id}',
            headers=foreign_headers,
        )
        self.assertEqual(foreign_profile.status_code, 404)

        foreign_tenant_repo_profile = self.client.get(
            f'/api/v1/config/profile/{tenant_repo_profile_id}',
            headers=foreign_headers,
        )
        self.assertEqual(foreign_tenant_repo_profile.status_code, 404)


if __name__ == '__main__':
    unittest.main()
