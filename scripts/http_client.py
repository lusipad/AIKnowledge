import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app.client import AiKnowledgeClientError, build_client_from_env


def _print_payload(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def run_demo(client) -> dict:
    session_response = client.create_session(
        {
            'repo_id': 'demo-repo',
            'branch_name': 'feature/http-demo',
            'task_id': 'DEMO-HTTP-1',
            'client_type': 'cli',
        }
    )
    session_id = session_response['data']['session_id']

    events_response = client.append_context_events(
        {
            'session_id': session_id,
            'events': [
                {
                    'event_type': 'prompt',
                    'summary': '订单风控规则必须通过统一规则引擎接入，并补充路径级回归检查项。',
                    'file_paths': ['src/order/risk/check.ts'],
                    'symbol_names': [],
                },
                {
                    'event_type': 'test_result',
                    'summary': '修复后回归通过，形成可复用案例。',
                    'file_paths': ['src/order/risk/check.ts'],
                    'symbol_names': [],
                },
            ],
        }
    )
    signal_ids = events_response['data']['created_signal_ids']

    extract_response = client.create_extract_task({'signal_ids': signal_ids, 'force': False})
    first_item = extract_response['data']['items'][0]
    knowledge_id = first_item['knowledge_id']

    client.review_knowledge(
        {
            'knowledge_id': knowledge_id,
            'decision': 'approve',
            'reviewer_id': 'demo-owner',
            'comment': 'HTTP demo auto approval',
        }
    )

    retrieval_response = client.retrieve_context_pack(
        {
            'session_id': session_id,
            'query': '为订单风控增加渠道黑名单校验',
            'query_type': 'feature_impl',
            'repo_id': 'demo-repo',
            'branch_name': 'feature/http-demo',
            'file_paths': ['src/order/risk/check.ts'],
            'token_budget': 2000,
        }
    )

    client.submit_knowledge_feedback(
        {
            'knowledge_id': knowledge_id,
            'request_id': retrieval_response['request_id'],
            'feedback_type': 'accepted',
            'feedback_score': 5,
            'feedback_text': 'HTTP demo accepted',
            'created_by': 'demo-user',
        }
    )

    client.submit_context_pack_feedback(
        {
            'request_id': retrieval_response['request_id'],
            'feedback_score': 4,
            'relevance_score': 5,
            'completeness_score': 4,
            'feedback_text': 'HTTP demo helpful',
            'created_by': 'demo-user',
        }
    )

    return {
        'session_id': session_id,
        'signal_ids': signal_ids,
        'knowledge_id': knowledge_id,
        'request_id': retrieval_response['request_id'],
        'context_summary': retrieval_response['data']['context_summary'],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='HTTP client for the AI knowledge MVP.')
    subparsers = parser.add_subparsers(dest='command', required=True)

    create_session_parser = subparsers.add_parser('create-session')
    create_session_parser.add_argument('--repo-id', required=True)
    create_session_parser.add_argument('--branch-name')
    create_session_parser.add_argument('--task-id')
    create_session_parser.add_argument('--client-type', default='cli')

    append_events_parser = subparsers.add_parser('append-events')
    append_events_parser.add_argument('--session-id', required=True)
    append_events_parser.add_argument('--events-json', required=True, help='JSON array of event objects')

    retrieve_parser = subparsers.add_parser('retrieve')
    retrieve_parser.add_argument('--session-id', required=True)
    retrieve_parser.add_argument('--query', required=True)
    retrieve_parser.add_argument('--repo-id')
    retrieve_parser.add_argument('--branch-name')
    retrieve_parser.add_argument('--query-type', default='general')
    retrieve_parser.add_argument('--file-path', action='append', default=[])
    retrieve_parser.add_argument('--token-budget', type=int, default=4000)

    subparsers.add_parser('demo')

    args = parser.parse_args()
    client = build_client_from_env()

    try:
        if args.command == 'create-session':
            payload = {
                'repo_id': args.repo_id,
                'branch_name': args.branch_name,
                'task_id': args.task_id,
                'client_type': args.client_type,
            }
            _print_payload(client.create_session(payload))
            return 0

        if args.command == 'append-events':
            payload = {
                'session_id': args.session_id,
                'events': json.loads(args.events_json),
            }
            _print_payload(client.append_context_events(payload))
            return 0

        if args.command == 'retrieve':
            payload = {
                'session_id': args.session_id,
                'query': args.query,
                'query_type': args.query_type,
                'repo_id': args.repo_id,
                'branch_name': args.branch_name,
                'file_paths': args.file_path,
                'token_budget': args.token_budget,
            }
            _print_payload(client.retrieve_context_pack(payload))
            return 0

        if args.command == 'demo':
            _print_payload(run_demo(client))
            return 0
    except AiKnowledgeClientError as exc:
        print(json.dumps({'status_code': exc.status_code, 'detail': exc.detail}, ensure_ascii=False, indent=2))
        return 1

    return 1


if __name__ == '__main__':
    raise SystemExit(main())
