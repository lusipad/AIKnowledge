import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app.client import build_client_from_env


def render_markdown(report: dict) -> str:
    lines = [
        f"# Evaluation Report: {report['scenario']['name']}",
        '',
        f"- Run ID: `{report['run_id']}`",
        f"- Status: `{report['status']}`",
        f"- Score: `{report['score']}`",
        f"- Summary: {report['summary']}",
        '',
        '## Categories',
    ]
    for category in report['categories']:
        lines.append(
            f"- `{category['category']}`: {category['score']}/{category['max_score']} ({category['status']})"
        )

    lines.append('')
    lines.append('## Critical Checks')
    for check in report['checks']:
        if check['critical']:
            state = 'PASS' if check['passed'] else 'FAIL'
            lines.append(f"- `{check['check_id']}` [{state}] {check['detail']}")

    lines.append('')
    lines.append('## Artifacts')
    for key, value in report['artifacts'].items():
        lines.append(f"- `{key}`: `{json.dumps(value, ensure_ascii=False)}`")

    return '\n'.join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description='Run the built-in system evaluation over HTTP.')
    parser.add_argument('--scenario-id', default='order_risk_regression_zh')
    parser.add_argument('--format', choices=['json', 'markdown'], default='markdown')
    parser.add_argument('--no-verify-llm', action='store_true')
    parser.add_argument('--no-persist', action='store_true')
    parser.add_argument('--repo-id')
    parser.add_argument('--branch-name')
    parser.add_argument('--task-id')
    parser.add_argument('--file-path')
    parser.add_argument('--profile-instruction')
    parser.add_argument('--event-prompt-summary')
    parser.add_argument('--event-result-summary')
    parser.add_argument('--query')
    parser.add_argument('--output')
    args = parser.parse_args()

    client = build_client_from_env()
    response = client.run_evaluation(
        {
            'scenario_id': args.scenario_id,
            'mode': 'full',
            'verify_llm': not args.no_verify_llm,
            'persist': not args.no_persist,
            'repo_id': args.repo_id,
            'branch_name': args.branch_name,
            'task_id': args.task_id,
            'file_path': args.file_path,
            'profile_instruction': args.profile_instruction,
            'event_prompt_summary': args.event_prompt_summary,
            'event_result_summary': args.event_result_summary,
            'query': args.query,
        }
    )['data']

    output_text = (
        json.dumps(response, ensure_ascii=False, indent=2)
        if args.format == 'json'
        else render_markdown(response)
    )
    print(output_text)

    if args.output:
        Path(args.output).write_text(output_text, encoding='utf-8')

    return 0 if response['status'] == 'ready' else 1


if __name__ == '__main__':
    raise SystemExit(main())
