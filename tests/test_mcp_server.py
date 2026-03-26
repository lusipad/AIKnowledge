import importlib.util
import unittest

import anyio

from app.client import AiKnowledgeClientError


HAS_MCP = importlib.util.find_spec('mcp') is not None
if HAS_MCP:
    from mcp.server.fastmcp.exceptions import ToolError


class FakeClient:
    def __init__(self):
        self.calls: list[tuple[str, object]] = []

    def request(self, method, path, payload=None, query=None):
        self.calls.append(('request', {'method': method, 'path': path, 'payload': payload, 'query': query}))
        return {'status': 'ok', 'path': path}

    def create_session(self, payload):
        self.calls.append(('create_session', payload))
        return {'data': {'session_id': 'sess_001', **payload}}

    def append_context_events(self, payload):
        self.calls.append(('append_context_events', payload))
        return {'data': {'created_signal_ids': ['sig_001']}}

    def create_graph_relation(self, payload):
        self.calls.append(('create_graph_relation', payload))
        return {'data': {'relation_id': 1, **payload}}

    def run_evaluation(self, payload):
        self.calls.append(('run_evaluation', payload))
        return {'data': {'run_id': 'eval_001', **payload}}


@unittest.skipUnless(HAS_MCP, 'mcp dependency not installed')
class McpServerTestCase(unittest.TestCase):
    def setUp(self):
        from app.mcp_server import build_mcp_server

        self.fake_client = FakeClient()
        self.server = build_mcp_server(client_factory=lambda: self.fake_client)

    def _call_tool(self, name: str, arguments: dict):
        async def run():
            return await self.server.call_tool(name, arguments)

        return anyio.run(run)

    def _list_tools(self):
        async def run():
            return await self.server.list_tools()

        return anyio.run(run)

    def test_server_exposes_core_tools(self):
        tools = self._list_tools()
        tool_names = {tool.name for tool in tools}
        self.assertIn('health_check', tool_names)
        self.assertIn('create_session', tool_names)
        self.assertIn('retrieve_context_pack', tool_names)
        self.assertIn('create_graph_relation', tool_names)
        self.assertIn('run_evaluation', tool_names)

    def test_create_session_tool_delegates_to_http_client(self):
        result = self._call_tool(
            'create_session',
            {
                'repo_id': 'repo-a',
                'branch_name': 'feature/mcp',
                'task_id': 'MCP-1',
                'client_type': 'agent',
            },
        )
        self.assertEqual(result[1]['data']['session_id'], 'sess_001')
        self.assertEqual(self.fake_client.calls[0][0], 'create_session')
        self.assertEqual(self.fake_client.calls[0][1]['repo_id'], 'repo-a')

    def test_append_context_events_serializes_nested_models(self):
        result = self._call_tool(
            'append_context_events',
            {
                'session_id': 'sess_001',
                'events': [
                    {
                        'event_type': 'prompt',
                        'summary': '订单风控规则必须进入统一引擎',
                        'file_paths': ['src/order/risk/check.ts'],
                        'symbol_names': [],
                    }
                ],
            },
        )
        self.assertEqual(result[1]['data']['created_signal_ids'], ['sig_001'])
        operation, payload = self.fake_client.calls[0]
        self.assertEqual(operation, 'append_context_events')
        self.assertEqual(payload['events'][0]['event_type'], 'prompt')

    def test_graph_relation_tool_returns_structured_payload(self):
        result = self._call_tool(
            'create_graph_relation',
            {
                'knowledge_id': 'kn_rule_001',
                'related_knowledge_id': 'kn_case_001',
                'relation_type': 'supersedes',
                'weight': 0.9,
            },
        )
        self.assertEqual(result[1]['data']['relation_type'], 'supersedes')
        self.assertEqual(self.fake_client.calls[0][0], 'create_graph_relation')

    def test_http_errors_are_raised_as_runtime_error(self):
        class ErrorClient(FakeClient):
            def run_evaluation(self, payload):
                raise AiKnowledgeClientError(403, '{"message":"insufficient role permissions"}')

        from app.mcp_server import build_mcp_server

        server = build_mcp_server(client_factory=ErrorClient)

        async def run():
            with self.assertRaisesRegex(ToolError, 'HTTP 403'):
                await server.call_tool('run_evaluation', {'scenario_id': 'order_risk_regression_zh'})

        anyio.run(run)
