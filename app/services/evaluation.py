from __future__ import annotations

import re
import time
from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import AuditLog, ContextPackFeedback, EvaluationRun, KnowledgeFeedback, utc_now
from app.request_context import get_request_context
from app.schemas import (
    ConfigProfileUpsertRequest,
    ContextEventsRequest,
    ContextPackFeedbackRequest,
    ExtractRequest,
    FeedbackRequest,
    ReviewRequest,
    RetrievalQueryRequest,
    SessionCreateRequest,
)
from app.services.llm_validation import verify_llm_connection
from app.services.use_cases import (
    append_context_events_data,
    create_extract_task_data,
    create_session_data,
    get_extract_task_data,
    get_knowledge_data,
    review_knowledge_data,
    retrieve_context_pack_data,
    submit_context_pack_feedback_data,
    submit_knowledge_feedback_data,
    upsert_profile_data,
)
from app.settings import AppSettings
from app.utils import api_response, generate_id, keyword_overlap_score


DEFAULT_SCENARIOS: dict[str, dict[str, Any]] = {
    'order_risk_regression_zh': {
        'name': '订单风控规则接入与回归治理',
        'description': '验证中文抽取、规则命中、审计透传、反馈闭环与整体延迟。',
        'repo_id': 'demo-repo',
        'branch_name': 'feature/order-risk-hardening',
        'task_id': 'EVAL-RISK-2048',
        'file_path': 'src/order/risk/check.ts',
        'profile_instructions': [
            '订单风控路径下的实现必须补充回归检查清单，并在涉及黑名单校验时记录命中原因。'
        ],
        'events': [
            {
                'event_type': 'prompt',
                'summary': '订单风控规则必须通过统一规则引擎接入，并补充路径级回归检查项，避免在订单入口散落特判逻辑。',
            },
            {
                'event_type': 'test_result',
                'summary': '修复后回归通过，形成可复用案例，并补充渠道黑名单命中原因记录，便于值班排查和复盘。',
            },
        ],
        'query': '为订单风控增加渠道黑名单校验与回归检查',
        'expect_cjk': True,
        'expected_signal_count': 2,
        'latency_budgets_ms': {
            'extract': 30000,
            'total': 45000,
        },
    }
}


@dataclass
class EvaluationCheck:
    check_id: str
    label: str
    category: str
    passed: bool
    weight: int
    detail: str
    expected: str | None = None
    actual: Any = None
    critical: bool = False

    @property
    def score(self) -> int:
        return self.weight if self.passed else 0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload['score'] = self.score
        return payload


def list_evaluation_scenarios() -> list[dict[str, Any]]:
    return [
        {
            'scenario_id': scenario_id,
            'name': item['name'],
            'description': item['description'],
            'repo_id': item['repo_id'],
            'branch_name': item['branch_name'],
            'file_path': item['file_path'],
            'query': item['query'],
            'expect_cjk': item['expect_cjk'],
        }
        for scenario_id, item in DEFAULT_SCENARIOS.items()
    ]


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r'[\u4e00-\u9fff]', text or ''))


def _normalize_report(run: EvaluationRun) -> dict[str, Any]:
    report = dict(run.report or {})
    report.update(
        {
            'run_id': run.run_id,
            'status': run.status,
            'score': float(run.score),
            'passed_checks': run.passed_checks,
            'total_checks': run.total_checks,
            'scenario_id': run.scenario_id,
            'mode': run.mode,
            'tenant_id': run.tenant_id,
            'team_id': run.team_id,
            'user_id': run.user_id,
            'created_at': run.created_at.isoformat(),
            'updated_at': run.updated_at.isoformat(),
        }
    )
    return report


def list_evaluation_runs(database: Session, *, limit: int = 20) -> list[dict[str, Any]]:
    runs = database.scalars(
        select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(max(1, min(limit, 100)))
    ).all()
    return [_normalize_report(run) for run in runs]


def get_evaluation_run(database: Session, run_id: str) -> dict[str, Any] | None:
    run = database.scalar(select(EvaluationRun).where(EvaluationRun.run_id == run_id))
    if not run:
        return None
    return _normalize_report(run)


def _resolve_scenario(payload: Any) -> dict[str, Any]:
    if payload.scenario_id not in DEFAULT_SCENARIOS:
        raise ValueError(f'unsupported scenario: {payload.scenario_id}')

    scenario = deepcopy(DEFAULT_SCENARIOS[payload.scenario_id])
    if payload.repo_id:
        scenario['repo_id'] = payload.repo_id
    if payload.branch_name:
        scenario['branch_name'] = payload.branch_name
    if payload.task_id:
        scenario['task_id'] = payload.task_id
    if payload.file_path:
        scenario['file_path'] = payload.file_path
    if payload.profile_instruction:
        scenario['profile_instructions'] = [payload.profile_instruction]
    if payload.event_prompt_summary:
        scenario['events'][0]['summary'] = payload.event_prompt_summary
    if payload.event_result_summary:
        scenario['events'][1]['summary'] = payload.event_result_summary
    if payload.query:
        scenario['query'] = payload.query
    return scenario


def _build_check(
    checks: list[EvaluationCheck],
    *,
    check_id: str,
    label: str,
    category: str,
    passed: bool,
    weight: int,
    detail: str,
    expected: str | None = None,
    actual: Any = None,
    critical: bool = False,
) -> None:
    checks.append(
        EvaluationCheck(
            check_id=check_id,
            label=label,
            category=category,
            passed=passed,
            weight=weight,
            detail=detail,
            expected=expected,
            actual=actual,
            critical=critical,
        )
    )


def _category_summary(checks: list[EvaluationCheck]) -> list[dict[str, Any]]:
    categories = []
    for category in ['availability', 'extraction', 'retrieval', 'governance', 'latency']:
        scoped = [item for item in checks if item.category == category]
        if not scoped:
            continue
        max_score = sum(item.weight for item in scoped)
        score = sum(item.score for item in scoped)
        failed_critical = [item.check_id for item in scoped if item.critical and not item.passed]
        categories.append(
            {
                'category': category,
                'score': score,
                'max_score': max_score,
                'status': 'pass' if not failed_critical and score >= max_score * 0.75 else 'needs_attention',
                'failed_critical_checks': failed_critical,
            }
        )
    return categories


def _database_session_ok(database: Session) -> tuple[bool, str]:
    try:
        database.execute(text('SELECT 1'))
        return True, 'ok'
    except Exception as exc:  # pragma: no cover - defensive
        return False, str(exc)


def run_evaluation(database: Session, settings: AppSettings, payload: Any) -> dict[str, Any]:
    request_context = get_request_context()
    scenario = _resolve_scenario(payload)
    run_id = generate_id('eval')
    started_at = utc_now()
    started_perf = time.perf_counter()
    steps: list[dict[str, Any]] = []
    checks: list[EvaluationCheck] = []
    artifacts: dict[str, Any] = {
        'scenario': {
            'scenario_id': payload.scenario_id,
            'name': scenario['name'],
            'repo_id': scenario['repo_id'],
            'branch_name': scenario['branch_name'],
            'task_id': scenario['task_id'],
            'file_path': scenario['file_path'],
            'query': scenario['query'],
        },
        'identity': {
            'request_id': request_context.request_id,
            'tenant_id': request_context.tenant_id,
            'team_id': request_context.team_id,
            'user_id': request_context.user_id,
            'client_type': request_context.client_type,
        },
        'llm': {
            'configured': settings.llm_configured,
            'model': settings.llm_model,
            'base_url': settings.llm_base_url,
        },
    }
    responses: dict[str, dict[str, Any]] = {}

    def as_response(data: dict[str, Any], *, request_id: str | None = None) -> dict[str, Any]:
        return api_response(data, request_id=request_id or request_context.request_id)

    def run_step(step_id: str, label: str, func):
        started = time.perf_counter()
        try:
            result = func()
            duration_ms = round((time.perf_counter() - started) * 1000)
            steps.append({'step_id': step_id, 'label': label, 'ok': True, 'duration_ms': duration_ms})
            return result, duration_ms, None
        except Exception as exc:  # pragma: no cover - defensive
            duration_ms = round((time.perf_counter() - started) * 1000)
            steps.append(
                {'step_id': step_id, 'label': label, 'ok': False, 'duration_ms': duration_ms, 'detail': str(exc)}
            )
            return None, duration_ms, exc

    db_ok, db_detail = _database_session_ok(database)
    _build_check(
        checks,
        check_id='db_session_ok',
        label='数据库会话可用',
        category='availability',
        passed=db_ok,
        weight=10,
        detail=db_detail,
        expected='SELECT 1 成功',
        actual=db_detail,
        critical=True,
    )
    _build_check(
        checks,
        check_id='request_context_attached',
        label='请求上下文已挂载',
        category='availability',
        passed=bool(request_context.request_id and request_context.client_type),
        weight=5,
        detail='request_id 和 client_type 已透传' if request_context.client_type else '缺少请求上下文字段',
        expected='request_id 与 client_type 存在',
        actual={'request_id': request_context.request_id, 'client_type': request_context.client_type},
        critical=True,
    )
    _build_check(
        checks,
        check_id='llm_configured',
        label='LLM 已配置',
        category='availability',
        passed=settings.llm_configured,
        weight=2,
        detail='已配置外部 LLM' if settings.llm_configured else '未配置外部 LLM，将使用启发式抽取',
        expected='AICODING_LLM_* 已配置',
        actual=artifacts['llm'],
    )

    llm_verify_result = None
    if payload.verify_llm and settings.llm_configured:
        llm_verify_result, _, _ = run_step(
            'verify_llm',
            '验证 LLM 连通性',
            lambda: verify_llm_connection(settings, prompt='Reply with ok only.', max_tokens=32),
        )
        _build_check(
            checks,
            check_id='llm_live_verify_ok',
            label='LLM 实时验证通过',
            category='availability',
            passed=bool(llm_verify_result and llm_verify_result.ok),
            weight=3,
            detail=llm_verify_result.detail if llm_verify_result else '未执行 LLM 验证',
            expected='返回 ok',
            actual=llm_verify_result.to_dict() if llm_verify_result else None,
        )
        artifacts['llm']['verify'] = llm_verify_result.to_dict() if llm_verify_result else None

    profile_id = generate_id('cfg_eval')
    profile_response, _, profile_error = run_step(
        'upsert_profile',
        '创建评估规则',
        lambda: as_response(
            upsert_profile_data(
                profile_id,
                ConfigProfileUpsertRequest(
                    scope_type='path',
                    scope_id=scenario['file_path'].rsplit('/', 1)[0],
                    profile_type='coding_rule',
                    content={'instructions': scenario['profile_instructions']},
                    version=1,
                    status='active',
                ),
                database,
                request_context=request_context,
            )
        ),
    )
    if profile_response:
        responses['profile'] = profile_response
        artifacts['profile_id'] = profile_id
    _build_check(
        checks,
        check_id='config_profile_created',
        label='评估规则写入成功',
        category='extraction',
        passed=bool(profile_response and profile_response['data']['profile_id'] == profile_id),
        weight=4,
        detail='规则已写入配置中心' if profile_response else str(profile_error),
        expected='返回 profile_id',
        actual=profile_response['data']['profile_id'] if profile_response else None,
        critical=True,
    )

    session_response = None
    if profile_response:
        session_response, _, session_error = run_step(
            'create_session',
            '创建评估会话',
            lambda: as_response(
                create_session_data(
                    SessionCreateRequest(
                        repo_id=scenario['repo_id'],
                        branch_name=scenario['branch_name'],
                        task_id=scenario['task_id'],
                        client_type=request_context.client_type or 'evaluation',
                    ),
                    database,
                    request_context=request_context,
                )
            ),
        )
        if session_response:
            responses['session'] = session_response
            artifacts['session_id'] = session_response['data']['session_id']
        _build_check(
            checks,
            check_id='session_created',
            label='评估会话创建成功',
            category='extraction',
            passed=bool(session_response and session_response['data']['session_id']),
            weight=4,
            detail='会话已创建' if session_response else str(session_error),
            expected='返回 session_id',
            actual=session_response['data']['session_id'] if session_response else None,
            critical=True,
        )

    events_response = None
    signal_ids: list[str] = []
    if session_response:
        events_response, _, events_error = run_step(
            'append_events',
            '上报场景事件',
            lambda: as_response(
                append_context_events_data(
                    ContextEventsRequest(
                        session_id=session_response['data']['session_id'],
                        events=[
                            {
                                'event_type': item['event_type'],
                                'summary': item['summary'],
                                'file_paths': [scenario['file_path']],
                                'symbol_names': ['validateOrderRisk'],
                            }
                            for item in scenario['events']
                        ],
                    ),
                    database,
                    request_context=request_context,
                )
            ),
        )
        if events_response:
            responses['events'] = events_response
            signal_ids = list(events_response['data']['created_signal_ids'])
            artifacts['signal_ids'] = signal_ids
        _build_check(
            checks,
            check_id='signals_generated',
            label='知识信号生成数量符合预期',
            category='extraction',
            passed=len(signal_ids) >= scenario['expected_signal_count'],
            weight=6,
            detail=f'已生成 {len(signal_ids)} 个信号' if signal_ids else str(events_error),
            expected=f'>={scenario["expected_signal_count"]} 个信号',
            actual=len(signal_ids),
            critical=True,
        )

    extract_response = None
    extract_task_response = None
    knowledge_response = None
    extracted_knowledge_ids: list[str] = []
    if signal_ids:
        extract_response, extract_duration_ms, extract_error = run_step(
            'extract_knowledge',
            '抽取知识',
            lambda: as_response(
                create_extract_task_data(
                    ExtractRequest(signal_ids=signal_ids, force=False),
                    database,
                    request_context=request_context,
                )
            ),
        )
        if extract_response:
            responses['extract'] = extract_response
            extracted_knowledge_ids = [item['knowledge_id'] for item in extract_response['data']['items']]
            artifacts['knowledge_ids'] = extracted_knowledge_ids
            first_item = extract_response['data']['items'][0]
            artifacts['extract_task_id'] = first_item['task_id']
            artifacts['knowledge_id'] = first_item['knowledge_id']
            extract_task_response = as_response(get_extract_task_data(first_item['task_id'], database))
            knowledge_response = as_response(get_knowledge_data(first_item['knowledge_id'], database))
            responses['extract_task'] = extract_task_response
            responses['knowledge'] = knowledge_response
            artifacts['extract_model_name'] = extract_task_response['data']['model_name']
            artifacts['extract_prompt_version'] = extract_task_response['data']['prompt_version']
        _build_check(
            checks,
            check_id='extract_task_success',
            label='知识抽取成功',
            category='extraction',
            passed=bool(extract_task_response and extract_task_response['data']['status'] == 'success'),
            weight=10,
            detail='抽取任务成功' if extract_task_response else str(extract_error),
            expected='extract task status=success',
            actual=extract_task_response['data']['status'] if extract_task_response else None,
            critical=True,
        )
        source_text = '\n'.join(item['summary'] for item in scenario['events'])
        knowledge_text = ''
        if knowledge_response:
            content = knowledge_response['data']['content']
            knowledge_text = '\n'.join(
                [
                    knowledge_response['data']['title'],
                    content.get('background', ''),
                    content.get('summary', ''),
                    content.get('conclusion', ''),
                ]
            )
        _build_check(
            checks,
            check_id='knowledge_grounded_in_source',
            label='知识内容与原始事件保持语义贴合',
            category='extraction',
            passed=keyword_overlap_score(source_text, knowledge_text) >= 0.15,
            weight=5,
            detail='关键词重合度达到阈值' if knowledge_text else '未获取知识详情',
            expected='keyword overlap >= 0.15',
            actual=round(keyword_overlap_score(source_text, knowledge_text), 4) if knowledge_text else 0,
            critical=True,
        )
        _build_check(
            checks,
            check_id='knowledge_language_preserved',
            label='中文输入输出语言保持一致',
            category='extraction',
            passed=(not scenario['expect_cjk']) or _contains_cjk(knowledge_text),
            weight=3,
            detail='知识输出保留中文' if _contains_cjk(knowledge_text) else '知识输出未保留中文',
            expected='中文场景输出中文',
            actual=knowledge_response['data']['title'] if knowledge_response else None,
        )
        _build_check(
            checks,
            check_id='extract_latency_budget',
            label='抽取耗时在预算内',
            category='latency',
            passed=extract_duration_ms <= scenario['latency_budgets_ms']['extract'],
            weight=4,
            detail=f'抽取耗时 {extract_duration_ms}ms',
            expected=f'<= {scenario["latency_budgets_ms"]["extract"]}ms',
            actual=extract_duration_ms,
        )

    review_response = None
    if extracted_knowledge_ids:
        review_response, _, review_error = run_step(
            'approve_knowledge',
            '审核知识并激活检索样本',
            lambda: [
                as_response(
                    review_knowledge_data(
                        ReviewRequest(
                            knowledge_id=knowledge_id,
                            decision='approve',
                            reviewer_id='evaluation-runner',
                            comment='Evaluation auto approval',
                        ),
                        database,
                    )
                )
                for knowledge_id in extracted_knowledge_ids
            ],
        )
        if review_response:
            responses['review'] = review_response
            artifacts['approved_knowledge_ids'] = extracted_knowledge_ids
            primary_knowledge_id = artifacts.get('knowledge_id')
            if primary_knowledge_id:
                knowledge_response = as_response(get_knowledge_data(primary_knowledge_id, database))
            responses['knowledge'] = knowledge_response
        _build_check(
            checks,
            check_id='knowledge_active_after_review',
            label='知识审核后变为 active',
            category='extraction',
            passed=bool(
                extracted_knowledge_ids
                and all(
                    get_knowledge_data(knowledge_id, database)['status'] == 'active'
                    for knowledge_id in extracted_knowledge_ids
                )
            ),
            weight=3,
            detail=f'已激活 {len(extracted_knowledge_ids)} 条知识' if review_response else str(review_error),
            expected='所有抽取知识均为 active',
            actual={
                knowledge_id: get_knowledge_data(knowledge_id, database)['status']
                for knowledge_id in extracted_knowledge_ids
            }
            if extracted_knowledge_ids
            else None,
            critical=True,
        )

    retrieval_response = None
    if session_response:
        retrieval_response, _, retrieval_error = run_step(
            'retrieve_context',
            '检索上下文包',
            lambda: (
                lambda context_pack, request_id: as_response(context_pack, request_id=request_id)
            )(
                *retrieve_context_pack_data(
                    RetrievalQueryRequest(
                        session_id=session_response['data']['session_id'],
                        query=scenario['query'],
                        query_type='feature_impl',
                        repo_id=scenario['repo_id'],
                        branch_name=scenario['branch_name'],
                        file_paths=[scenario['file_path']],
                        token_budget=2200,
                    ),
                    database,
                    request_context=request_context,
                )
            ),
        )
        if retrieval_response:
            responses['retrieval'] = retrieval_response
            artifacts['retrieval_request_id'] = retrieval_response['request_id']
        retrieval_sources = retrieval_response['data']['sources'] if retrieval_response else []
        _build_check(
            checks,
            check_id='retrieval_has_request_id',
            label='检索请求号已生成',
            category='retrieval',
            passed=bool(retrieval_response and retrieval_response['request_id']),
            weight=4,
            detail='检索请求已写入日志' if retrieval_response else str(retrieval_error),
            expected='request_id 存在',
            actual=retrieval_response['request_id'] if retrieval_response else None,
            critical=True,
        )
        _build_check(
            checks,
            check_id='retrieval_has_context_summary',
            label='上下文包包含摘要',
            category='retrieval',
            passed=bool(retrieval_response and retrieval_response['data']['context_summary']),
            weight=4,
            detail='上下文包已生成摘要' if retrieval_response else str(retrieval_error),
            expected='context_summary 非空',
            actual=retrieval_response['data']['context_summary'] if retrieval_response else None,
            critical=True,
        )
        _build_check(
            checks,
            check_id='retrieval_hits_generated_knowledge',
            label='检索命中本次生成的知识',
            category='retrieval',
            passed=bool(
                retrieval_response
                and any(item['knowledge_id'] == artifacts.get('knowledge_id') for item in retrieval_sources)
            ),
            weight=10,
            detail='已命中本次生成知识' if retrieval_response else '未检索到数据',
            expected='sources 包含 knowledge_id',
            actual=retrieval_sources,
            critical=True,
        )
        generated_knowledge_ids = set(artifacts.get('approved_knowledge_ids') or artifacts.get('knowledge_ids') or [])
        generated_knowledge_rank = next(
            (index + 1 for index, item in enumerate(retrieval_sources) if item['knowledge_id'] in generated_knowledge_ids),
            None,
        )
        config_source_count = len([item for item in retrieval_sources if item.get('source_type') == 'config_profile'])
        context_summary = retrieval_response['data']['context_summary'] if retrieval_response else ''
        _build_check(
            checks,
            check_id='retrieval_generated_knowledge_prominent',
            label='本次生成知识位于前排结果',
            category='retrieval',
            passed=generated_knowledge_rank is not None and generated_knowledge_rank <= 3,
            weight=6,
            detail=f'生成知识排名为第 {generated_knowledge_rank} 位' if generated_knowledge_rank else '未进入 sources',
            expected='generated knowledge rank <= 3',
            actual={'rank': generated_knowledge_rank, 'sources': retrieval_sources[:5]},
            critical=True,
        )
        _build_check(
            checks,
            check_id='retrieval_summary_query_relevant',
            label='上下文摘要与查询保持相关',
            category='retrieval',
            passed=keyword_overlap_score(scenario['query'], context_summary) >= 0.18,
            weight=5,
            detail='摘要与查询关键词保持相关' if context_summary else '摘要为空',
            expected='keyword overlap >= 0.18',
            actual=round(keyword_overlap_score(scenario['query'], context_summary), 4) if context_summary else 0,
            critical=True,
        )
        primary_knowledge_text = ''
        if knowledge_response:
            primary_content = knowledge_response['data']['content']
            primary_knowledge_text = '\n'.join(
                [
                    knowledge_response['data']['title'],
                    primary_content.get('conclusion', ''),
                    primary_content.get('summary', ''),
                ]
            )
        _build_check(
            checks,
            check_id='retrieval_summary_mentions_primary_knowledge',
            label='上下文摘要能体现主知识结论',
            category='retrieval',
            passed=bool(context_summary) and keyword_overlap_score(primary_knowledge_text, context_summary) >= 0.1,
            weight=4,
            detail='摘要已体现主知识内容' if context_summary else '摘要为空',
            expected='summary overlaps primary knowledge >= 0.1',
            actual=round(keyword_overlap_score(primary_knowledge_text, context_summary), 4) if context_summary else 0,
        )
        _build_check(
            checks,
            check_id='retrieval_config_rules_bounded',
            label='配置规则数量受控，不淹没检索结果',
            category='retrieval',
            passed=config_source_count <= 3,
            weight=4,
            detail=f'config sources={config_source_count}',
            expected='config source count <= 3',
            actual=config_source_count,
        )

    if retrieval_response and knowledge_response:
        run_step(
            'submit_feedback',
            '写入反馈',
            lambda: (
                as_response(
                    submit_knowledge_feedback_data(
                        FeedbackRequest(
                            knowledge_id=knowledge_response['data']['knowledge_id'],
                            request_id=retrieval_response['request_id'],
                            feedback_type='accepted',
                            feedback_score=5,
                            feedback_text='Evaluation accepted',
                            created_by=request_context.user_id or 'evaluation-runner',
                        ),
                        database,
                        request_context=request_context,
                    )
                ),
                as_response(
                    submit_context_pack_feedback_data(
                        ContextPackFeedbackRequest(
                            request_id=retrieval_response['request_id'],
                            feedback_score=5,
                            relevance_score=5,
                            completeness_score=4,
                            feedback_text='Evaluation helpful',
                            created_by=request_context.user_id or 'evaluation-runner',
                        ),
                        database,
                        request_context=request_context,
                    )
                ),
            ),
        )
        knowledge_feedback_count = len(
            database.scalars(
                select(KnowledgeFeedback).where(KnowledgeFeedback.knowledge_id == knowledge_response['data']['knowledge_id'])
            ).all()
        )
        context_feedback_count = len(
            database.scalars(
                select(ContextPackFeedback).where(ContextPackFeedback.request_id == retrieval_response['request_id'])
            ).all()
        )
        _build_check(
            checks,
            check_id='feedback_recorded',
            label='知识与上下文反馈均已记录',
            category='governance',
            passed=knowledge_feedback_count >= 1 and context_feedback_count >= 1,
            weight=3,
            detail=f'knowledge_feedback={knowledge_feedback_count}, context_feedback={context_feedback_count}',
            expected='两个反馈表均至少 1 条',
            actual={'knowledge_feedback': knowledge_feedback_count, 'context_feedback': context_feedback_count},
        )

    relevant_resource_ids = {
        item
        for item in [
            artifacts.get('profile_id'),
            artifacts.get('session_id'),
            artifacts.get('knowledge_id'),
            artifacts.get('retrieval_request_id'),
        ]
        if item
    }
    audit_logs = database.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(200)).all()
    relevant_audit_logs = [log for log in audit_logs if log.resource_id in relevant_resource_ids]
    audit_context_ok = any(
        log.detail.get('tenant_id') == request_context.tenant_id
        and log.detail.get('team_id') == request_context.team_id
        and log.detail.get('client_type') == request_context.client_type
        for log in relevant_audit_logs
    )
    _build_check(
        checks,
        check_id='audit_context_propagated',
        label='审计日志保留租户/团队/客户端上下文',
        category='governance',
        passed=audit_context_ok,
        weight=7,
        detail=f'匹配到 {len(relevant_audit_logs)} 条相关审计日志',
        expected='相关 audit detail 含 tenant_id/team_id/client_type',
        actual=[{'action': log.action, 'detail': log.detail} for log in relevant_audit_logs[:5]],
        critical=True,
    )

    response_request_ids = {
        name: item.get('request_id')
        for name, item in responses.items()
        if isinstance(item, dict) and item.get('request_id')
    }
    _build_check(
        checks,
        check_id='response_request_ids_present',
        label='核心响应都包含 request_id',
        category='retrieval',
        passed=all(key in response_request_ids for key in ['profile', 'session', 'events', 'extract', 'retrieval'] if key in responses),
        weight=4,
        detail='核心响应均带 request_id' if response_request_ids else '未收集到 request_id',
        expected='主要 API 响应含 request_id',
        actual=response_request_ids,
    )

    total_duration_ms = round((time.perf_counter() - started_perf) * 1000)
    _build_check(
        checks,
        check_id='total_latency_budget',
        label='整体评估耗时在预算内',
        category='latency',
        passed=total_duration_ms <= scenario['latency_budgets_ms']['total'],
        weight=6,
        detail=f'总耗时 {total_duration_ms}ms',
        expected=f'<= {scenario["latency_budgets_ms"]["total"]}ms',
        actual=total_duration_ms,
    )

    score = sum(item.score for item in checks)
    max_score = sum(item.weight for item in checks)
    failed_critical_checks = [item.check_id for item in checks if item.critical and not item.passed]
    ratio = (score / max_score) if max_score else 0
    if failed_critical_checks and ratio < 0.6:
        status = 'blocked'
    elif failed_critical_checks or ratio < 0.85:
        status = 'needs_attention'
    else:
        status = 'ready'

    report = {
        'run_id': run_id,
        'scenario_id': payload.scenario_id,
        'scenario': {
            'scenario_id': payload.scenario_id,
            'name': scenario['name'],
            'description': scenario['description'],
            'repo_id': scenario['repo_id'],
            'branch_name': scenario['branch_name'],
            'task_id': scenario['task_id'],
            'file_path': scenario['file_path'],
            'query': scenario['query'],
        },
        'mode': payload.mode,
        'status': status,
        'score': round((score / max_score) * 100, 2) if max_score else 0,
        'score_breakdown': {'achieved': score, 'max_score': max_score},
        'passed_checks': len([item for item in checks if item.passed]),
        'total_checks': len(checks),
        'failed_critical_checks': failed_critical_checks,
        'summary': (
            '评估通过，关键链路可用于真实场景演示与常规使用。'
            if status == 'ready'
            else '评估已完成，但仍有指标需要关注。'
            if status == 'needs_attention'
            else '评估阻塞，关键链路未通过。'
        ),
        'categories': _category_summary(checks),
        'checks': [item.to_dict() for item in checks],
        'steps': steps,
        'artifacts': artifacts,
        'created_at': started_at.isoformat(),
        'completed_at': utc_now().isoformat(),
        'durations': {
            'total_ms': total_duration_ms,
            'step_durations_ms': {step['step_id']: step['duration_ms'] for step in steps},
        },
    }

    if payload.persist:
        run = EvaluationRun(
            run_id=run_id,
            tenant_id=request_context.tenant_id,
            team_id=request_context.team_id,
            user_id=request_context.user_id,
            scenario_id=payload.scenario_id,
            mode=payload.mode,
            status=status,
            score=report['score'],
            passed_checks=report['passed_checks'],
            total_checks=report['total_checks'],
            report=report,
        )
        database.add(run)
        database.commit()
        database.refresh(run)
        return _normalize_report(run)

    return report
