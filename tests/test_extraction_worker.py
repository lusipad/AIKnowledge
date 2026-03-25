import os
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.schemas import ContextEventsRequest, ExtractRequest, ReviewRequest, SessionCreateRequest
from app.services.bootstrap import seed_default_profiles
from app.services.use_cases import (
    append_context_events_data,
    create_extract_task_data,
    create_session_data,
    get_extract_task_data,
    process_pending_extract_tasks_data,
    review_knowledge_data,
)


class ExtractionWorkerTestCase(unittest.TestCase):
    def setUp(self):
        self.previous_extraction_mode = os.environ.get('AICODING_EXTRACTION_MODE')
        os.environ['AICODING_EXTRACTION_MODE'] = 'async'

        self.engine = create_engine(
            'sqlite://',
            connect_args={'check_same_thread': False},
            poolclass=StaticPool,
        )
        self.SessionTesting = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, expire_on_commit=False)
        Base.metadata.create_all(bind=self.engine)
        self.database = self.SessionTesting()
        seed_default_profiles(self.database)

    def tearDown(self):
        self.database.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()
        if self.previous_extraction_mode is None:
            os.environ.pop('AICODING_EXTRACTION_MODE', None)
        else:
            os.environ['AICODING_EXTRACTION_MODE'] = self.previous_extraction_mode

    def test_async_extract_task_can_be_processed_by_worker(self):
        session_response = create_session_data(
            SessionCreateRequest(
                repo_id='demo-repo',
                branch_name='feature/async-extract',
                task_id='TASK-ASYNC-1',
                client_type='cli',
            ),
            self.database,
        )
        session_id = session_response['session_id']

        events_response = append_context_events_data(
            ContextEventsRequest(
                session_id=session_id,
                events=[
                    {
                        'event_type': 'prompt',
                        'summary': '订单风控规则必须通过统一规则引擎接入',
                        'file_paths': ['src/order/risk/check.ts'],
                        'symbol_names': [],
                    }
                ],
            ),
            self.database,
        )
        signal_id = events_response['created_signal_ids'][0]

        extract_response = create_extract_task_data(ExtractRequest(signal_ids=[signal_id], force=False), self.database)
        item = extract_response['items'][0]
        self.assertEqual(item['status'], 'pending')
        self.assertIsNone(item['knowledge_id'])

        task_detail_before = get_extract_task_data(item['task_id'], self.database)
        self.assertEqual(task_detail_before['status'], 'pending')
        self.assertIsNone(task_detail_before['result_ref'])

        worker_result = process_pending_extract_tasks_data(self.database, limit=10)
        self.database.commit()
        self.assertEqual(worker_result['processed_count'], 1)
        self.assertEqual(worker_result['items'][0]['status'], 'success')

        task_detail_after = get_extract_task_data(item['task_id'], self.database)
        self.assertEqual(task_detail_after['status'], 'success')
        self.assertIsNotNone(task_detail_after['result_ref'])

        review_response = review_knowledge_data(
            ReviewRequest(
                knowledge_id=task_detail_after['result_ref'],
                decision='approve',
                reviewer_id='async-worker-reviewer',
            ),
            self.database,
        )
        self.assertEqual(review_response['status'], 'active')


if __name__ == '__main__':
    unittest.main()
