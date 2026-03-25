import io
import json
import unittest
import urllib.error

from app.models import ConversationSession, KnowledgeSignal, SessionEvent
from app.services.extraction import build_heuristic_draft, extract_knowledge_draft
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


def _build_settings(**overrides) -> AppSettings:
    defaults = {
        'app_name': 'AI Coding Knowledge & Memory MVP',
        'app_version': '0.4.0',
        'db_url': 'sqlite:///:memory:',
        'vector_backend': 'simple',
        'api_key': None,
        'env': 'test',
        'llm_base_url': 'https://example.com',
        'llm_api_key': 'secret',
        'llm_model': 'gpt-5.4-low',
        'llm_chat_path': '/v1/chat/completions',
        'llm_timeout_sec': 10,
    }
    defaults.update(overrides)
    return AppSettings(**defaults)


def _build_fixtures():
    session = ConversationSession(
        session_id='sess_001',
        repo_id='demo-repo',
        branch_name='feature/demo',
        task_id='TASK-1',
        client_type='cli',
    )
    signal = KnowledgeSignal(
        signal_id='sig_001',
        session_id='sess_001',
        signal_type='rule',
        confidence=0.82,
        priority=80,
        status='pending',
        source_refs={
            'summary': '订单风控规则必须通过统一规则引擎接入',
            'file_paths': ['src/order/risk/check.ts'],
        },
    )
    events = [
        SessionEvent(
            session_id='sess_001',
            event_type='prompt',
            summary='订单风控规则必须通过统一规则引擎接入',
            file_paths=['src/order/risk/check.ts'],
            symbol_names=[],
        )
    ]
    return session, signal, events


class ExtractionServiceTestCase(unittest.TestCase):
    def test_build_heuristic_draft(self):
        session, signal, events = _build_fixtures()
        draft = build_heuristic_draft(signal, session, events)
        self.assertEqual(draft.knowledge_type, 'rule')
        self.assertEqual(draft.content['scope_type'], 'path')
        self.assertIn('demo-repo', draft.content['tags'])

    def test_extract_knowledge_draft_prefers_llm_when_available(self):
        session, signal, events = _build_fixtures()

        def fake_urlopen(request, timeout):
            return _FakeResponse(
                {
                    'choices': [
                        {
                            'message': {
                                'content': json.dumps(
                                    {
                                        'title': '规则：订单风控统一规则引擎接入',
                                        'knowledge_type': 'rule',
                                        'memory_type': 'semantic',
                                        'background': '订单风控模块新增能力。',
                                        'conclusion': '所有风控规则必须通过统一规则引擎接入。',
                                        'summary': '统一入口能减少重复逻辑。',
                                        'tags': ['risk', 'engine'],
                                        'scope_type': 'path',
                                        'scope_id': 'src/order/risk',
                                        'applicability': {'repo_id': 'demo-repo', 'file_paths': ['src/order/risk/check.ts']},
                                        'invalidation_signals': ['规则引擎迁移'],
                                        'confidence_score': 0.93,
                                    },
                                    ensure_ascii=False,
                                )
                            }
                        }
                    ]
                }
            )

        draft = extract_knowledge_draft(
            signal,
            session,
            events,
            settings=_build_settings(),
            urlopen=fake_urlopen,
        )
        self.assertEqual(draft.model_name, 'gpt-5.4-low')
        self.assertEqual(draft.content['scope_id'], 'src/order/risk')
        self.assertIn('risk', draft.content['tags'])

    def test_extract_knowledge_draft_falls_back_on_gateway_error(self):
        session, signal, events = _build_fixtures()

        def fake_urlopen(request, timeout):
            raise urllib.error.HTTPError(
                url=request.full_url,
                code=403,
                msg='Forbidden',
                hdrs=None,
                fp=io.BytesIO(b'error code: 1010'),
            )

        draft = extract_knowledge_draft(
            signal,
            session,
            events,
            settings=_build_settings(),
            urlopen=fake_urlopen,
        )
        self.assertEqual(draft.model_name, 'heuristic-extractor')
        self.assertEqual(draft.content['scope_type'], 'path')


if __name__ == '__main__':
    unittest.main()
