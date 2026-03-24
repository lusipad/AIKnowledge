import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

runtime_dir = ROOT_DIR / 'runtime'
runtime_dir.mkdir(exist_ok=True)
os.environ.setdefault('AICODING_DB_URL', 'sqlite:///./runtime/demo_flow.db')

from app.database import Base, SessionLocal, engine
from app.routers.context import append_context_events
from app.routers.knowledge import create_extract_task, review_knowledge
from app.routers.retrieval import retrieve_context_pack
from app.routers.sessions import create_session
from app.schemas import ContextEventsRequest, ExtractRequest, RetrievalQueryRequest, ReviewRequest, SessionCreateRequest
from app.services.bootstrap import seed_default_profiles


Base.metadata.create_all(bind=engine)
database = SessionLocal()
seed_default_profiles(database)

session_response = create_session(
    SessionCreateRequest(
        repo_id='demo-repo',
        branch_name='feature/demo',
        task_id='DEMO-1',
        client_type='cli',
    ),
    database,
)
session_id = session_response['data']['session_id']

append_response = append_context_events(
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
    database,
)

extract_response = create_extract_task(
    ExtractRequest(signal_ids=append_response['data']['created_signal_ids']),
    database,
)
knowledge_id = extract_response['data']['items'][0]['knowledge_id']
review_knowledge(ReviewRequest(knowledge_id=knowledge_id, decision='approve', reviewer_id='demo-owner'), database)

retrieval_response = retrieve_context_pack(
    RetrievalQueryRequest(
        session_id=session_id,
        query='新增订单风控渠道黑名单能力',
        query_type='feature_impl',
        repo_id='demo-repo',
        file_paths=['src/order/risk/check.ts'],
    ),
    database,
)

print('session_id:', session_id)
print('knowledge_id:', knowledge_id)
print('request_id:', retrieval_response['request_id'])
print('context_summary:', retrieval_response['data']['context_summary'])

database.close()
