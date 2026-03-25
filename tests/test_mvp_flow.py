import os
import unittest

os.environ['AICODING_DB_URL'] = 'sqlite:///:memory:'

from app.database import Base, SessionLocal, engine
from app.routers.audit import list_audit_logs
from app.routers.config import get_profile, get_profiles, rollback_profile, upsert_profile
from app.routers.context import append_context_events, list_signals
from app.routers.feedback import submit_context_pack_feedback, submit_knowledge_feedback
from app.routers.knowledge import (
    create_extract_task,
    deprecate_knowledge,
    get_extract_task,
    get_knowledge,
    list_knowledge,
    list_knowledge_reviews,
    review_knowledge,
    update_knowledge,
)
from app.routers.retrieval import debug_retrieval, get_retrieval_log, list_retrieval_logs, retrieve_context_pack
from app.routers.sessions import create_session, list_sessions
from app.schemas import (
    ConfigProfileUpsertRequest,
    ConfigRollbackRequest,
    ContextEventsRequest,
    ContextPackFeedbackRequest,
    ExtractRequest,
    FeedbackRequest,
    KnowledgeDeprecateRequest,
    KnowledgeUpdateRequest,
    RetrievalQueryRequest,
    ReviewRequest,
    SessionCreateRequest,
)
from app.services.bootstrap import seed_default_profiles


class MvpFlowTestCase(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.database = SessionLocal()
        seed_default_profiles(self.database)

    def tearDown(self):
        self.database.close()
        engine.dispose()

    def test_end_to_end_flow(self):
        session_response = create_session(
            SessionCreateRequest(
                repo_id='demo-repo',
                branch_name='feature/order-risk-check',
                task_id='ISSUE-1024',
                client_type='ide',
            ),
            self.database,
        )
        session_id = session_response['data']['session_id']
        self.assertTrue(session_id.startswith('sess_'))
        sessions_response = list_sessions(repo_id='demo-repo', page=1, page_size=10, database=self.database)
        self.assertGreaterEqual(sessions_response['data']['total'], 1)
        self.assertEqual(sessions_response['data']['items'][0]['session_id'], session_id)
        self.assertEqual(sessions_response['data']['items'][0]['event_count'], 0)
        self.assertEqual(sessions_response['data']['items'][0]['signal_count'], 0)

        events_response = append_context_events(
            ContextEventsRequest(
                session_id=session_id,
                events=[
                    {
                        'event_type': 'prompt',
                        'summary': '订单风控规则必须通过统一规则引擎接入',
                        'file_paths': ['src/order/risk/check.ts'],
                        'symbol_names': [],
                    },
                    {
                        'event_type': 'test_result',
                        'summary': '修复后回归通过，补充回归检查清单',
                        'file_paths': ['src/order/risk/check.ts'],
                        'symbol_names': [],
                    },
                ],
            ),
            self.database,
        )
        self.assertEqual(events_response['data']['accepted_count'], 2)
        signal_ids = events_response['data']['created_signal_ids']
        self.assertEqual(len(signal_ids), 2)

        signals_response = list_signals(None, self.database)
        self.assertGreaterEqual(len(signals_response['data']), 2)

        sessions_after_events = list_sessions(repo_id='demo-repo', page=1, page_size=10, database=self.database)
        self.assertEqual(sessions_after_events['data']['items'][0]['event_count'], 2)
        self.assertEqual(sessions_after_events['data']['items'][0]['signal_count'], 2)

        extract_response = create_extract_task(ExtractRequest(signal_ids=signal_ids, force=False), self.database)
        self.assertEqual(len(extract_response['data']['items']), 2)
        task_id = extract_response['data']['items'][0]['task_id']
        knowledge_id = extract_response['data']['items'][0]['knowledge_id']
        deduplicated_extract = create_extract_task(ExtractRequest(signal_ids=signal_ids, force=False), self.database)
        self.assertTrue(deduplicated_extract['data']['items'][0]['deduplicated'])

        extract_task = get_extract_task(task_id, self.database)
        self.assertEqual(extract_task['data']['status'], 'success')

        review_response = review_knowledge(
            ReviewRequest(knowledge_id=knowledge_id, decision='approve', reviewer_id='tl_001'),
            self.database,
        )
        self.assertEqual(review_response['data']['status'], 'active')

        update_response = update_knowledge(
            knowledge_id,
            KnowledgeUpdateRequest(title='规则：订单风控统一规则引擎接入', status='active'),
            self.database,
        )
        self.assertEqual(update_response['data']['version'], 2)

        knowledge_detail = get_knowledge(knowledge_id, self.database)
        self.assertEqual(knowledge_detail['data']['title'], '规则：订单风控统一规则引擎接入')

        reviews = list_knowledge_reviews(knowledge_id, self.database)
        self.assertEqual(len(reviews['data']), 1)

        retrieval_response = retrieve_context_pack(
            RetrievalQueryRequest(
                session_id=session_id,
                query='为订单风控增加渠道黑名单校验',
                query_type='feature_impl',
                repo_id='demo-repo',
                branch_name='feature/order-risk-check',
                file_paths=['src/order/risk/check.ts'],
                token_budget=2000,
            ),
            self.database,
        )
        request_id = retrieval_response['request_id']
        self.assertTrue(request_id.startswith('ret_'))
        self.assertIn('rules', retrieval_response['data'])

        debug_response = debug_retrieval(
            RetrievalQueryRequest(
                session_id=session_id,
                query='订单风控规则怎么接入',
                query_type='rule_lookup',
                repo_id='demo-repo',
                file_paths=['src/order/risk/check.ts'],
            ),
            self.database,
        )
        self.assertIn('debug', debug_response['data'])

        knowledge_feedback = submit_knowledge_feedback(
            FeedbackRequest(
                knowledge_id=knowledge_id,
                request_id=request_id,
                feedback_type='accepted',
                feedback_score=5,
                feedback_text='命中准确',
                created_by='dev_001',
            ),
            self.database,
        )
        self.assertGreaterEqual(knowledge_feedback['data']['quality_score'], 0.8)

        context_feedback = submit_context_pack_feedback(
            ContextPackFeedbackRequest(
                request_id=request_id,
                feedback_score=4,
                relevance_score=5,
                completeness_score=4,
                feedback_text='整体有帮助',
                created_by='dev_001',
            ),
            self.database,
        )
        self.assertEqual(context_feedback['data']['status'], 'recorded')

        profiles = get_profiles(scope_type='repo', scope_id='demo-repo', profile_type='prompt', database=self.database)
        profile_id = profiles['data'][0]['profile_id']
        upsert_profile(
            profile_id,
            ConfigProfileUpsertRequest(
                scope_type='repo',
                scope_id='demo-repo',
                profile_type='prompt',
                content={'instructions': ['所有风控变更必须补充回归检查项。']},
                version=2,
                status='active',
            ),
            self.database,
        )
        rollback_response = rollback_profile(
            profile_id,
            ConfigRollbackRequest(target_version=1, actor_id='admin_001'),
            self.database,
        )
        self.assertEqual(rollback_response['data']['restored_from'], 1)

        profile_detail = get_profile(profile_id, self.database)
        self.assertGreaterEqual(len(profile_detail['data']['history']), 2)

        deprecated = deprecate_knowledge(
            knowledge_id,
            KnowledgeDeprecateRequest(actor_id='admin_001', reason='规则已迁移到新服务'),
            self.database,
        )
        self.assertEqual(deprecated['data']['status'], 'deprecated')

        knowledge_list = list_knowledge(
            scope_type='path',
            scope_id='src/order/risk',
            knowledge_type=None,
            memory_type=None,
            status=None,
            keyword='demo-repo',
            page=1,
            page_size=20,
            database=self.database,
        )
        self.assertGreaterEqual(len(knowledge_list['data']['items']), 1)
        self.assertGreaterEqual(knowledge_list['data']['total'], 1)

        retrieval_logs = list_retrieval_logs(session_id=session_id, database=self.database)
        self.assertGreaterEqual(len(retrieval_logs['data']), 1)
        self.assertEqual(retrieval_logs['data'][0]['knowledge_feedback_count'], 1)
        self.assertEqual(retrieval_logs['data'][0]['context_feedback']['feedback_score'], 4)

        retrieval_log_detail = get_retrieval_log(request_id, self.database)
        self.assertEqual(retrieval_log_detail['data']['request_id'], request_id)
        self.assertGreaterEqual(len(retrieval_log_detail['data']['results']), 1)
        self.assertEqual(len(retrieval_log_detail['data']['context_pack_feedback']), 1)
        self.assertEqual(len(retrieval_log_detail['data']['knowledge_feedback']), 1)

        audit_logs = list_audit_logs(limit=50, action=None, resource_type=None, database=self.database)
        self.assertGreaterEqual(len(audit_logs['data']), 1)


if __name__ == '__main__':
    unittest.main()
