from __future__ import annotations

import json
from typing import Any, Callable

from pydantic import BaseModel, Field

from app.client import AiKnowledgeClientError, build_client_from_env
from app.schemas import DirectoryGroupUpsertRequest, DirectoryUserUpsertRequest, SessionEventInput

try:  # pragma: no cover - exercised in MCP-enabled environments
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - exercised when MCP dependency is absent
    FastMCP = None  # type: ignore[assignment]
    MCP_IMPORT_ERROR = exc
else:  # pragma: no cover - trivial branch
    MCP_IMPORT_ERROR = None


class KnowledgeFeedbackInput(BaseModel):
    knowledge_id: str
    request_id: str | None = None
    feedback_type: str
    feedback_score: int
    feedback_text: str | None = None
    created_by: str = 'user'


class ContextPackFeedbackInput(BaseModel):
    request_id: str
    feedback_score: int
    relevance_score: int | None = None
    completeness_score: int | None = None
    feedback_text: str | None = None
    created_by: str = 'user'


ClientFactory = Callable[[], Any]


def _ensure_mcp_available():
    if FastMCP is None:
        raise RuntimeError(
            'MCP SDK is not installed. Install dependencies from requirements-mcp.txt in a dedicated MCP environment.'
        ) from MCP_IMPORT_ERROR


def _normalize_payload(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(exclude_none=True)
    if isinstance(value, list):
        return [_normalize_payload(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_payload(item) for key, item in value.items() if item is not None}
    return value


def _format_client_error(operation: str, exc: AiKnowledgeClientError) -> str:
    detail = exc.detail
    try:
        parsed = json.loads(exc.detail)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        detail = parsed.get('detail') or parsed.get('message') or exc.detail

    if exc.status_code is None:
        return f'{operation} failed: {detail}'
    return f'{operation} failed with HTTP {exc.status_code}: {detail}'


def _invoke(client_factory: ClientFactory, operation: str, callback: Callable[[Any], Any]) -> Any:
    client = client_factory()
    try:
        return callback(client)
    except AiKnowledgeClientError as exc:
        raise RuntimeError(_format_client_error(operation, exc)) from exc


def _overview_markdown() -> str:
    return """# AIKnowledge MCP Server

This MCP server wraps the running AIKnowledge HTTP service and exposes its core workflows as MCP tools.

Environment variables used by the server process:

- `AICODING_API_BASE_URL`
- `AICODING_API_KEY`
- `AICODING_TENANT_ID`
- `AICODING_TEAM_ID`
- `AICODING_USER_ID`
- `AICODING_USER_ROLE`
- `AICODING_CLIENT_TYPE`

Recommended tool flow:

1. `health_check`
2. `create_session`
3. `append_context_events`
4. `create_extract_task`
5. `review_knowledge`
6. `retrieve_context_pack`
7. `create_graph_relation` / `get_knowledge_graph`
8. `run_evaluation`
"""


def build_mcp_server(
    *,
    client_factory: ClientFactory = build_client_from_env,
    host: str = '127.0.0.1',
    port: int = 8765,
    mount_path: str = '/',
    streamable_http_path: str = '/mcp',
    log_level: str = 'INFO',
):
    _ensure_mcp_available()
    server = FastMCP(
        name='AIKnowledge',
        instructions=(
            'Use these tools to operate the AIKnowledge HTTP service. '
            'Prefer create_session -> append_context_events -> create_extract_task -> '
            'review_knowledge -> retrieve_context_pack for the main workflow. '
            'Use graph and directory tools only when the caller has sufficient role permissions.'
        ),
        website_url='https://github.com/lusipad/AIKnowledge',
        host=host,
        port=port,
        mount_path=mount_path,
        streamable_http_path=streamable_http_path,
        log_level=log_level.upper(),
    )

    @server.resource(
        'aiknowledge://overview',
        name='AIKnowledge Overview',
        description='High-level usage guidance for the AIKnowledge MCP server.',
        mime_type='text/markdown',
    )
    def overview_resource() -> str:
        return _overview_markdown()

    @server.resource(
        'aiknowledge://health',
        name='AIKnowledge Health Snapshot',
        description='Fetch the current /readyz response from the backing AIKnowledge service.',
        mime_type='application/json',
    )
    def health_resource() -> str:
        payload = _invoke(client_factory, 'health_check', lambda client: client.request('GET', '/readyz'))
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @server.tool(description='Check whether the backing AIKnowledge service is ready.')
    def health_check() -> dict[str, Any]:
        return _invoke(client_factory, 'health_check', lambda client: client.request('GET', '/readyz'))

    @server.tool(description='Create a new coding session for a repo/branch/task.')
    def create_session(
        repo_id: str,
        branch_name: str | None = None,
        task_id: str | None = None,
        client_type: str = 'cli',
    ) -> dict[str, Any]:
        return _invoke(
            client_factory,
            'create_session',
            lambda client: client.create_session(
                {
                    'repo_id': repo_id,
                    'branch_name': branch_name,
                    'task_id': task_id,
                    'client_type': client_type,
                }
            ),
        )

    @server.tool(description='List sessions filtered by repo, status, task, or client type.')
    def list_sessions(
        repo_id: str | None = None,
        status: str | None = None,
        client_type: str | None = None,
        task_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        return _invoke(
            client_factory,
            'list_sessions',
            lambda client: client.list_sessions(
                repo_id=repo_id,
                status=status,
                client_type=client_type,
                task_id=task_id,
                page=page,
                page_size=page_size,
            ),
        )

    @server.tool(description='Append prompt/test/deploy events to an existing session.')
    def append_context_events(session_id: str, events: list[SessionEventInput]) -> dict[str, Any]:
        return _invoke(
            client_factory,
            'append_context_events',
            lambda client: client.append_context_events(
                {
                    'session_id': session_id,
                    'events': _normalize_payload(events),
                }
            ),
        )

    @server.tool(description='Create knowledge extraction tasks from signal IDs.')
    def create_extract_task(signal_ids: list[str], force: bool = False) -> dict[str, Any]:
        return _invoke(
            client_factory,
            'create_extract_task',
            lambda client: client.create_extract_task({'signal_ids': signal_ids, 'force': force}),
        )

    @server.tool(description='Get the latest state of a knowledge extraction task.')
    def get_extract_task(task_id: str) -> dict[str, Any]:
        return _invoke(client_factory, 'get_extract_task', lambda client: client.get_extract_task(task_id))

    @server.tool(description='Approve or reject a knowledge item as reviewer.')
    def review_knowledge(
        knowledge_id: str,
        decision: str,
        comment: str | None = None,
        reviewer_id: str = 'reviewer',
    ) -> dict[str, Any]:
        return _invoke(
            client_factory,
            'review_knowledge',
            lambda client: client.review_knowledge(
                {
                    'knowledge_id': knowledge_id,
                    'decision': decision,
                    'comment': comment,
                    'reviewer_id': reviewer_id,
                }
            ),
        )

    @server.tool(description='Retrieve a context pack for the current coding task.')
    def retrieve_context_pack(
        session_id: str,
        query: str,
        query_type: str = 'general',
        repo_id: str | None = None,
        branch_name: str | None = None,
        file_paths: list[str] | None = None,
        token_budget: int = 4000,
    ) -> dict[str, Any]:
        return _invoke(
            client_factory,
            'retrieve_context_pack',
            lambda client: client.retrieve_context_pack(
                {
                    'session_id': session_id,
                    'query': query,
                    'query_type': query_type,
                    'repo_id': repo_id,
                    'branch_name': branch_name,
                    'file_paths': file_paths or [],
                    'token_budget': token_budget,
                }
            ),
        )

    @server.tool(description='List retrieval logs for a session or repo.')
    def list_retrieval_logs(
        session_id: str | None = None,
        repo_id: str | None = None,
        query_type: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        return _invoke(
            client_factory,
            'list_retrieval_logs',
            lambda client: client.list_retrieval_logs(
                session_id=session_id,
                repo_id=repo_id,
                query_type=query_type,
                limit=limit,
            ),
        )

    @server.tool(description='Fetch one retrieval log entry by request_id.')
    def get_retrieval_log(request_id: str) -> dict[str, Any]:
        return _invoke(client_factory, 'get_retrieval_log', lambda client: client.get_retrieval_log(request_id))

    @server.tool(description='Submit user feedback for one knowledge item.')
    def submit_knowledge_feedback(payload: KnowledgeFeedbackInput) -> dict[str, Any]:
        return _invoke(
            client_factory,
            'submit_knowledge_feedback',
            lambda client: client.submit_knowledge_feedback(_normalize_payload(payload)),
        )

    @server.tool(description='Submit feedback for a retrieved context pack.')
    def submit_context_pack_feedback(payload: ContextPackFeedbackInput) -> dict[str, Any]:
        return _invoke(
            client_factory,
            'submit_context_pack_feedback',
            lambda client: client.submit_context_pack_feedback(_normalize_payload(payload)),
        )

    @server.tool(description='List visible knowledge items by scope or keyword.')
    def list_knowledge(
        scope_type: str | None = None,
        scope_id: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        return _invoke(
            client_factory,
            'list_knowledge',
            lambda client: client.list_knowledge(
                scope_type=scope_type,
                scope_id=scope_id,
                keyword=keyword,
                page=page,
                page_size=page_size,
            ),
        )

    @server.tool(description='Fetch one visible knowledge item by ID.')
    def get_knowledge(knowledge_id: str) -> dict[str, Any]:
        return _invoke(client_factory, 'get_knowledge', lambda client: client.get_knowledge(knowledge_id))

    @server.tool(description='List built-in evaluation scenarios.')
    def list_evaluation_scenarios() -> dict[str, Any]:
        return _invoke(client_factory, 'list_evaluation_scenarios', lambda client: client.list_evaluation_scenarios())

    @server.tool(description='Run the built-in evaluation pipeline against the current scope.')
    def run_evaluation(
        scenario_id: str = 'order_risk_regression_zh',
        mode: str = 'full',
        verify_llm: bool = True,
        persist: bool = True,
        repo_id: str | None = None,
        branch_name: str | None = None,
        task_id: str | None = None,
        file_path: str | None = None,
        profile_instruction: str | None = None,
        event_prompt_summary: str | None = None,
        event_result_summary: str | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        return _invoke(
            client_factory,
            'run_evaluation',
            lambda client: client.run_evaluation(
                {
                    'scenario_id': scenario_id,
                    'mode': mode,
                    'verify_llm': verify_llm,
                    'persist': persist,
                    'repo_id': repo_id,
                    'branch_name': branch_name,
                    'task_id': task_id,
                    'file_path': file_path,
                    'profile_instruction': profile_instruction,
                    'event_prompt_summary': event_prompt_summary,
                    'event_result_summary': event_result_summary,
                    'query': query,
                }
            ),
        )

    @server.tool(description='List historical evaluation runs.')
    def list_evaluation_runs(limit: int = 20) -> dict[str, Any]:
        return _invoke(client_factory, 'list_evaluation_runs', lambda client: client.list_evaluation_runs(limit=limit))

    @server.tool(description='Fetch one evaluation run detail by run_id.')
    def get_evaluation_run(run_id: str) -> dict[str, Any]:
        return _invoke(client_factory, 'get_evaluation_run', lambda client: client.get_evaluation_run(run_id))

    @server.tool(description='List visible directory users from the SCIM-backed directory mirror.')
    def list_directory_users() -> dict[str, Any]:
        return _invoke(client_factory, 'list_directory_users', lambda client: client.list_directory_users())

    @server.tool(description='List visible directory groups from the SCIM-backed directory mirror.')
    def list_directory_groups() -> dict[str, Any]:
        return _invoke(client_factory, 'list_directory_groups', lambda client: client.list_directory_groups())

    @server.tool(description='Upsert one SCIM-style directory user.')
    def upsert_directory_user(
        user_id: str,
        tenant_id: str | None = None,
        team_id: str | None = None,
        external_ref: str | None = None,
        email: str | None = None,
        display_name: str | None = None,
        active: bool = True,
        attributes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = DirectoryUserUpsertRequest(
            tenant_id=tenant_id,
            team_id=team_id,
            external_ref=external_ref,
            email=email,
            display_name=display_name,
            active=active,
            attributes=attributes or {},
        )
        return _invoke(
            client_factory,
            'upsert_directory_user',
            lambda client: client.upsert_directory_user(user_id, _normalize_payload(payload)),
        )

    @server.tool(description='Upsert one SCIM-style directory group and membership mapping.')
    def upsert_directory_group(
        group_id: str,
        display_name: str,
        scope_type: str = 'team',
        scope_id: str | None = None,
        tenant_id: str | None = None,
        team_id: str | None = None,
        external_ref: str | None = None,
        mapped_role: str | None = None,
        active: bool = True,
        member_user_ids: list[str] | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = DirectoryGroupUpsertRequest(
            tenant_id=tenant_id,
            team_id=team_id,
            external_ref=external_ref,
            display_name=display_name,
            scope_type=scope_type,
            scope_id=scope_id,
            mapped_role=mapped_role,
            active=active,
            member_user_ids=member_user_ids or [],
            attributes=attributes or {},
        )
        return _invoke(
            client_factory,
            'upsert_directory_group',
            lambda client: client.upsert_directory_group(group_id, _normalize_payload(payload)),
        )

    @server.tool(description='Bulk sync users and groups into the directory mirror.')
    def sync_directory(
        users: dict[str, DirectoryUserUpsertRequest] | None = None,
        groups: dict[str, DirectoryGroupUpsertRequest] | None = None,
    ) -> dict[str, Any]:
        return _invoke(
            client_factory,
            'sync_directory',
            lambda client: client.sync_directory(
                {
                    'users': _normalize_payload(users or {}),
                    'groups': _normalize_payload(groups or {}),
                }
            ),
        )

    @server.tool(description='Create or update a cross-repo knowledge graph relation.')
    def create_graph_relation(
        knowledge_id: str,
        related_knowledge_id: str,
        relation_type: str,
        repo_id: str | None = None,
        related_repo_id: str | None = None,
        weight: float = 1.0,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return _invoke(
            client_factory,
            'create_graph_relation',
            lambda client: client.create_graph_relation(
                {
                    'knowledge_id': knowledge_id,
                    'related_knowledge_id': related_knowledge_id,
                    'relation_type': relation_type,
                    'repo_id': repo_id,
                    'related_repo_id': related_repo_id,
                    'weight': weight,
                    'detail': detail or {},
                }
            ),
        )

    @server.tool(description='Get the visible graph view around one knowledge item.')
    def get_knowledge_graph(knowledge_id: str) -> dict[str, Any]:
        return _invoke(client_factory, 'get_knowledge_graph', lambda client: client.get_knowledge_graph(knowledge_id))

    @server.tool(description='Get the visible knowledge map for one repo, including cross-repo edges.')
    def get_repo_knowledge_map(repo_id: str) -> dict[str, Any]:
        return _invoke(client_factory, 'get_repo_knowledge_map', lambda client: client.get_repo_knowledge_map(repo_id))

    return server
