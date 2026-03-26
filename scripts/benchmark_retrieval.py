import argparse
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app.client import AiKnowledgeClientError, build_client_from_env


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    session_id: str
    query: str
    query_type: str
    repo_id: str | None
    branch_name: str | None
    file_paths: list[str]
    token_budget: int


@dataclass(frozen=True)
class BenchmarkSample:
    case_id: str
    iteration: int
    duration_ms: float
    success: bool
    source_count: int
    rule_count: int
    error: str | None = None


def compute_percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    if percentile <= 0:
        return min(values)
    if percentile >= 1:
        return max(values)

    sorted_values = sorted(values)
    rank = (len(sorted_values) - 1) * percentile
    lower_index = math.floor(rank)
    upper_index = math.ceil(rank)
    lower_value = sorted_values[lower_index]
    upper_value = sorted_values[upper_index]
    if lower_index == upper_index:
        return lower_value
    weight = rank - lower_index
    return lower_value + (upper_value - lower_value) * weight


def summarize_samples(samples: list[BenchmarkSample]) -> dict[str, Any]:
    success_samples = [item for item in samples if item.success]
    success_durations = [item.duration_ms for item in success_samples]
    total_requests = len(samples)
    success_count = len(success_samples)
    error_count = total_requests - success_count
    total_duration_ms = sum(item.duration_ms for item in samples)
    return {
        'total_requests': total_requests,
        'success_count': success_count,
        'error_count': error_count,
        'success_rate': round(success_count / total_requests, 4) if total_requests else 0.0,
        'throughput_rps': round((success_count * 1000 / total_duration_ms), 4) if total_duration_ms > 0 else 0.0,
        'latency_ms': {
            'min': round(min(success_durations), 3) if success_durations else 0.0,
            'max': round(max(success_durations), 3) if success_durations else 0.0,
            'avg': round(sum(success_durations) / len(success_durations), 3) if success_durations else 0.0,
            'p50': round(compute_percentile(success_durations, 0.50), 3),
            'p95': round(compute_percentile(success_durations, 0.95), 3),
            'p99': round(compute_percentile(success_durations, 0.99), 3),
        },
    }


def load_benchmark_cases(dataset_path: str) -> list[dict[str, Any]]:
    payload = json.loads(Path(dataset_path).read_text(encoding='utf-8'))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get('items'), list):
        return payload['items']
    raise ValueError('benchmark dataset must be a JSON array or an object with an "items" array')


def create_session_for_case(client, *, repo_id: str, branch_name: str | None, task_id: str | None) -> str:
    response = client.create_session(
        {
            'repo_id': repo_id,
            'branch_name': branch_name,
            'task_id': task_id,
            'client_type': 'benchmark',
        }
    )
    return response['data']['session_id']


def normalize_case(item: dict[str, Any], *, default_session_id: str | None = None) -> BenchmarkCase:
    session_id = item.get('session_id') or default_session_id
    if not session_id:
        raise ValueError(f'benchmark case {item.get("case_id") or "unknown"} is missing session_id')
    return BenchmarkCase(
        case_id=item.get('case_id') or f'case_{abs(hash((session_id, item.get("query", "")))) % 100000:05d}',
        session_id=session_id,
        query=item['query'],
        query_type=item.get('query_type') or 'feature_impl',
        repo_id=item.get('repo_id'),
        branch_name=item.get('branch_name'),
        file_paths=list(item.get('file_paths') or []),
        token_budget=max(1, int(item.get('token_budget') or 4000)),
    )


def execute_case(client, case: BenchmarkCase, iteration: int) -> BenchmarkSample:
    started_at = time.perf_counter()
    try:
        response = client.retrieve_context_pack(
            {
                'session_id': case.session_id,
                'query': case.query,
                'query_type': case.query_type,
                'repo_id': case.repo_id,
                'branch_name': case.branch_name,
                'file_paths': case.file_paths,
                'token_budget': case.token_budget,
            }
        )['data']
        duration_ms = (time.perf_counter() - started_at) * 1000
        return BenchmarkSample(
            case_id=case.case_id,
            iteration=iteration,
            duration_ms=duration_ms,
            success=True,
            source_count=len(response.get('sources') or []),
            rule_count=len(response.get('rules') or []),
        )
    except AiKnowledgeClientError as exc:
        duration_ms = (time.perf_counter() - started_at) * 1000
        return BenchmarkSample(
            case_id=case.case_id,
            iteration=iteration,
            duration_ms=duration_ms,
            success=False,
            source_count=0,
            rule_count=0,
            error=exc.detail,
        )


def run_benchmark(
    client,
    *,
    cases: list[BenchmarkCase],
    iterations: int,
    warmup: int,
    concurrency: int,
) -> dict[str, Any]:
    warmup_samples: list[BenchmarkSample] = []
    for _ in range(max(0, warmup)):
        for case in cases:
            warmup_samples.append(execute_case(client, case, iteration=0))

    benchmark_samples: list[BenchmarkSample] = []
    started_at = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as executor:
        futures = [
            executor.submit(execute_case, client, case, iteration)
            for iteration in range(1, max(1, iterations) + 1)
            for case in cases
        ]
        for future in as_completed(futures):
            benchmark_samples.append(future.result())
    elapsed_ms = (time.perf_counter() - started_at) * 1000

    per_case: dict[str, list[BenchmarkSample]] = {}
    for sample in benchmark_samples:
        per_case.setdefault(sample.case_id, []).append(sample)

    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'concurrency': max(1, concurrency),
        'warmup_requests': len(warmup_samples),
        'benchmark_requests': len(benchmark_samples),
        'elapsed_ms': round(elapsed_ms, 3),
        'summary': summarize_samples(benchmark_samples),
        'cases': [
            {
                'case_id': case.case_id,
                'query': case.query,
                'repo_id': case.repo_id,
                'branch_name': case.branch_name,
                'summary': summarize_samples(per_case.get(case.case_id, [])),
            }
            for case in cases
        ],
        'samples': [asdict(sample) for sample in sorted(benchmark_samples, key=lambda item: (item.case_id, item.iteration))],
    }


def render_markdown(report: dict[str, Any]) -> str:
    latency = report['summary']['latency_ms']
    lines = [
        '# Retrieval Benchmark Report',
        '',
        f"- Generated At: `{report['generated_at']}`",
        f"- Concurrency: `{report['concurrency']}`",
        f"- Warmup Requests: `{report['warmup_requests']}`",
        f"- Benchmark Requests: `{report['benchmark_requests']}`",
        f"- Elapsed: `{report['elapsed_ms']}ms`",
        '',
        '## Summary',
        f"- Success Rate: `{report['summary']['success_rate']}`",
        f"- Throughput: `{report['summary']['throughput_rps']} rps`",
        f"- Latency: `avg={latency['avg']}ms p50={latency['p50']}ms p95={latency['p95']}ms p99={latency['p99']}ms max={latency['max']}ms`",
        '',
        '## Cases',
    ]
    for case in report['cases']:
        case_latency = case['summary']['latency_ms']
        lines.append(
            f"- `{case['case_id']}`: avg `{case_latency['avg']}ms`, p95 `{case_latency['p95']}ms`, "
            f"success `{case['summary']['success_rate']}`"
        )
    return '\n'.join(lines)


def build_cases_from_args(args, client) -> list[BenchmarkCase]:
    if args.dataset:
        return [normalize_case(item) for item in load_benchmark_cases(args.dataset)]

    if not args.query:
        raise ValueError('either --dataset or --query is required')
    if not args.session_id and not args.repo_id:
        raise ValueError('when --session-id is omitted, --repo-id is required to create a benchmark session')

    session_id = args.session_id
    if not session_id:
        session_id = create_session_for_case(
            client,
            repo_id=args.repo_id,
            branch_name=args.branch_name,
            task_id=args.task_id,
        )

    return [
        normalize_case(
            {
                'case_id': args.case_id or 'inline_case',
                'session_id': session_id,
                'query': args.query,
                'query_type': args.query_type,
                'repo_id': args.repo_id,
                'branch_name': args.branch_name,
                'file_paths': args.file_path or [],
                'token_budget': args.token_budget,
            }
        )
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description='Benchmark retrieval latency and throughput over HTTP.')
    parser.add_argument('--dataset')
    parser.add_argument('--case-id')
    parser.add_argument('--session-id')
    parser.add_argument('--repo-id')
    parser.add_argument('--branch-name')
    parser.add_argument('--task-id')
    parser.add_argument('--query')
    parser.add_argument('--query-type', default='feature_impl')
    parser.add_argument('--file-path', action='append')
    parser.add_argument('--token-budget', type=int, default=4000)
    parser.add_argument('--iterations', type=int, default=5)
    parser.add_argument('--warmup', type=int, default=1)
    parser.add_argument('--concurrency', type=int, default=1)
    parser.add_argument('--format', choices=['json', 'markdown'], default='markdown')
    parser.add_argument('--output')
    args = parser.parse_args()

    client = build_client_from_env()
    cases = build_cases_from_args(args, client)
    report = run_benchmark(
        client,
        cases=cases,
        iterations=max(1, args.iterations),
        warmup=max(0, args.warmup),
        concurrency=max(1, args.concurrency),
    )

    output_text = json.dumps(report, ensure_ascii=False, indent=2) if args.format == 'json' else render_markdown(report)
    print(output_text)
    if args.output:
        Path(args.output).write_text(output_text, encoding='utf-8')
    return 0 if report['summary']['error_count'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
