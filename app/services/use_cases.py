from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ConfigProfile,
    ConfigProfileVersion,
    ContextPackFeedback,
    ConversationSession,
    ExtractTask,
    KnowledgeCandidate,
    KnowledgeFeedback,
    KnowledgeItem,
    KnowledgeReview,
    KnowledgeSignal,
    KnowledgeSourceRef,
    RetrievalRequest,
    RetrievalResult,
    SessionEvent,
)
from app.request_context import RequestContext, get_request_context
from app.schemas import (
    ConfigProfileUpsertRequest,
    ContextEventsRequest,
    ContextPackFeedbackRequest,
    ExtractRequest,
    FeedbackRequest,
    RetrievalQueryRequest,
    ReviewRequest,
    SessionCreateRequest,
)
from app.services.audit import append_audit_log
from app.services.extraction import extract_knowledge_draft
from app.services.freshness import apply_knowledge_freshness_updates
from app.services.isolation import (
    apply_config_scope,
    apply_knowledge_scope,
    apply_retrieval_request_scope,
    apply_session_scope,
)
from app.services.retrieval import (
    build_context_summary,
    dedupe_ranked_entries,
    order_context_sources,
    rank_config_rules,
    rank_knowledge_items,
    scope_matches,
    select_config_rules,
)
from app.services.signals import build_signal_from_event
from app.settings import load_settings
from app.utils import generate_id


class ResourceNotFoundError(ValueError):
    pass


class InvalidOperationError(ValueError):
    pass


class AuthorizationError(ValueError):
    pass


def _resolve_request_context(request_context: RequestContext | None = None) -> RequestContext:
    return request_context or get_request_context()


def _get_scoped_session(
    database: Session,
    session_id: str,
    *,
    request_context: RequestContext | None = None,
) -> ConversationSession | None:
    return database.scalar(
        apply_session_scope(select(ConversationSession).where(ConversationSession.session_id == session_id), request_context)
    )


def _get_scoped_knowledge(
    database: Session,
    knowledge_id: str,
    *,
    request_context: RequestContext | None = None,
) -> KnowledgeItem | None:
    return database.scalar(
        apply_knowledge_scope(select(KnowledgeItem).where(KnowledgeItem.knowledge_id == knowledge_id), request_context)
    )


def _get_scoped_extract_task(
    database: Session,
    task_id: str,
    *,
    request_context: RequestContext | None = None,
) -> ExtractTask | None:
    statement = (
        select(ExtractTask)
        .join(KnowledgeCandidate, KnowledgeCandidate.candidate_id == ExtractTask.candidate_id)
        .join(KnowledgeSignal, KnowledgeSignal.signal_id == KnowledgeCandidate.signal_id)
        .join(ConversationSession, ConversationSession.session_id == KnowledgeSignal.session_id)
        .where(ExtractTask.task_id == task_id)
    )
    return database.scalar(apply_session_scope(statement, request_context))


def _get_scoped_signal_rows(
    database: Session,
    signal_ids: list[str],
    *,
    request_context: RequestContext | None = None,
) -> list[KnowledgeSignal]:
    statement = (
        select(KnowledgeSignal)
        .join(ConversationSession, ConversationSession.session_id == KnowledgeSignal.session_id)
        .where(KnowledgeSignal.signal_id.in_(signal_ids))
    )
    return database.scalars(apply_session_scope(statement, request_context)).all()


def _assert_profile_scope_writable(
    *,
    scope_type: str,
    scope_id: str,
    request_context: RequestContext,
) -> None:
    if scope_type not in {'global', 'repo', 'path', 'tenant', 'team'}:
        raise InvalidOperationError('unsupported config scope type')

    if request_context.tenant_id:
        if scope_type == 'tenant':
            if scope_id != f'tenant:{request_context.tenant_id}':
                raise AuthorizationError('tenant scoped profile is not writable in current tenant context')
            return
        if scope_type == 'team':
            if not request_context.team_id:
                raise AuthorizationError('team scoped profile requires team context')
            expected_scope_id = f'team:{request_context.tenant_id}:{request_context.team_id}'
            if scope_id != expected_scope_id:
                raise AuthorizationError('team scoped profile is not writable in current team context')
            return
        raise AuthorizationError('shared global/repo/path profiles require platform context')

    if scope_type in {'tenant', 'team'}:
        raise AuthorizationError('tenant/team scoped profiles require tenant context')


def ensure_profile_writable(profile: ConfigProfile, request_context: RequestContext | None = None) -> None:
    _assert_profile_scope_writable(
        scope_type=profile.scope_type,
        scope_id=profile.scope_id,
        request_context=_resolve_request_context(request_context),
    )


def create_session_data(
    payload: SessionCreateRequest,
    database: Session,
    *,
    request_context: RequestContext | None = None,
) -> dict:
    current_context = _resolve_request_context(request_context)
    client_type = current_context.client_type or payload.client_type
    session = ConversationSession(
        session_id=generate_id('sess'),
        tenant_id=current_context.tenant_id,
        team_id=current_context.team_id,
        user_id=current_context.user_id,
        repo_id=payload.repo_id,
        branch_name=payload.branch_name,
        task_id=payload.task_id,
        client_type=client_type,
    )
    database.add(session)
    append_audit_log(
        database,
        actor_id=current_context.user_id or 'system',
        action='session.create',
        resource_type='session',
        resource_id=session.session_id,
        scope_type='repo',
        scope_id=payload.repo_id,
        detail={
            'branch_name': payload.branch_name,
            'task_id': payload.task_id,
            'client_type': client_type,
        },
    )
    database.commit()
    database.refresh(session)
    return {
        'session_id': session.session_id,
        'tenant_id': session.tenant_id,
        'team_id': session.team_id,
        'user_id': session.user_id,
        'repo_id': session.repo_id,
        'branch_name': session.branch_name,
        'task_id': session.task_id,
        'started_at': session.started_at.isoformat(),
        'status': session.status,
        'client_type': session.client_type,
    }


def append_context_events_data(
    payload: ContextEventsRequest,
    database: Session,
    *,
    request_context: RequestContext | None = None,
) -> dict:
    current_context = _resolve_request_context(request_context)
    session = _get_scoped_session(database, payload.session_id, request_context=current_context)
    if not session:
        raise ResourceNotFoundError('session not found')

    accepted_count = 0
    created_signal_ids: list[str] = []
    freshness_updates: list[dict] = []
    for item in payload.events:
        event = SessionEvent(
            session_id=payload.session_id,
            event_type=item.event_type,
            event_subtype=item.event_subtype,
            summary=item.summary,
            content_ref=item.content_ref,
            tool_name=item.tool_name,
            file_paths=item.file_paths,
            symbol_names=item.symbol_names,
            event_time=item.timestamp,
        )
        database.add(event)
        database.flush()
        accepted_count += 1

        signal = build_signal_from_event(event)
        if signal:
            database.add(signal)
            created_signal_ids.append(signal.signal_id)

        updates = apply_knowledge_freshness_updates(
            database,
            session=session,
            event=event,
            actor_id=current_context.user_id or session.user_id or 'system',
        )
        freshness_updates.extend(
            [
                {
                    'knowledge_id': update.knowledge_id,
                    'action': update.action,
                    'status': update.status,
                    'freshness_score': update.freshness_score,
                    'matched_signals': update.matched_signals,
                    'overlap_score': update.overlap_score,
                }
                for update in updates
            ]
        )

    append_audit_log(
        database,
        actor_id=current_context.user_id or session.user_id or 'system',
        action='context.events.append',
        resource_type='session',
        resource_id=payload.session_id,
        scope_type='repo',
        scope_id=session.repo_id,
        detail={
            'accepted_count': accepted_count,
            'created_signal_ids': created_signal_ids,
            'freshness_updates': freshness_updates,
        },
    )
    database.commit()
    return {
        'session_id': payload.session_id,
        'accepted_count': accepted_count,
        'rejected_count': 0,
        'created_signal_ids': created_signal_ids,
        'freshness_updates': freshness_updates,
    }


def _record_profile_version(database: Session, profile: ConfigProfile) -> None:
    database.add(
        ConfigProfileVersion(
            profile_id=profile.profile_id,
            version=profile.version,
            content=profile.content,
            status=profile.status,
        )
    )


def upsert_profile_data(
    profile_id: str,
    payload: ConfigProfileUpsertRequest,
    database: Session,
    *,
    request_context: RequestContext | None = None,
) -> dict:
    current_context = _resolve_request_context(request_context)
    _assert_profile_scope_writable(
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        request_context=current_context,
    )
    profile_exists = database.scalar(select(ConfigProfile.profile_id).where(ConfigProfile.profile_id == profile_id))
    profile = database.scalar(
        apply_config_scope(select(ConfigProfile).where(ConfigProfile.profile_id == profile_id), current_context)
    )
    if profile_id and profile_exists and not profile:
        raise ResourceNotFoundError('profile not found')
    if profile:
        _assert_profile_scope_writable(
            scope_type=profile.scope_type,
            scope_id=profile.scope_id,
            request_context=current_context,
        )
        profile.scope_type = payload.scope_type
        profile.scope_id = payload.scope_id
        profile.profile_type = payload.profile_type
        profile.content = payload.content
        profile.version = max(profile.version + 1, payload.version)
        profile.status = payload.status
    else:
        profile = ConfigProfile(
            profile_id=profile_id or generate_id('cfg'),
            scope_type=payload.scope_type,
            scope_id=payload.scope_id,
            profile_type=payload.profile_type,
            content=payload.content,
            version=max(1, payload.version),
            status=payload.status,
        )
        database.add(profile)

    _record_profile_version(database, profile)
    append_audit_log(
        database,
        actor_id=current_context.user_id or 'system',
        action='config.upsert',
        resource_type='config',
        resource_id=profile.profile_id,
        scope_type=profile.scope_type,
        scope_id=profile.scope_id,
        detail={'profile_type': profile.profile_type, 'version': profile.version},
    )
    database.commit()
    return {
        'profile_id': profile.profile_id,
        'scope_type': profile.scope_type,
        'scope_id': profile.scope_id,
        'profile_type': profile.profile_type,
        'version': profile.version,
        'status': profile.status,
    }


def _load_signal_context(
    database: Session,
    signal: KnowledgeSignal,
    *,
    request_context: RequestContext | None = None,
) -> tuple[ConversationSession | None, list[SessionEvent], str]:
    session = _get_scoped_session(database, signal.session_id, request_context=request_context)
    events = database.scalars(
        select(SessionEvent).where(SessionEvent.session_id == signal.session_id).order_by(SessionEvent.event_time.desc()).limit(10)
    ).all()
    joined_summary = '\n'.join(event.summary for event in reversed(events)) or signal.source_refs.get('summary', '')
    return session, events, joined_summary


def _create_candidate_from_signal(database: Session, signal: KnowledgeSignal) -> KnowledgeCandidate:
    session, _, joined_summary = _load_signal_context(database, signal)
    candidate = KnowledgeCandidate(
        candidate_id=generate_id('cand'),
        signal_id=signal.signal_id,
        candidate_type=signal.signal_type if signal.signal_type in {'rule', 'case', 'procedure'} else 'rule',
        summary=joined_summary[:1500],
        scope_hint={
            'scope_type': 'repo' if session else 'global',
            'scope_id': session.repo_id if session else 'global',
        },
        quality_score=float(signal.confidence),
        extract_prompt_version='queued',
        status='pending',
    )
    database.add(candidate)
    database.flush()
    return candidate


def _create_extract_task_record(
    database: Session,
    candidate: KnowledgeCandidate,
    *,
    settings,
) -> ExtractTask:
    task = ExtractTask(
        task_id=generate_id('ext'),
        candidate_id=candidate.candidate_id,
        status='pending',
        model_name=settings.llm_model or 'heuristic-extractor',
        prompt_version='queued',
        result_ref=None,
    )
    database.add(task)
    database.flush()
    return task


def _execute_extract_task(
    database: Session,
    *,
    signal: KnowledgeSignal,
    candidate: KnowledgeCandidate,
    task: ExtractTask,
    settings,
    actor_id: str,
    request_context: RequestContext | None = None,
) -> KnowledgeItem:
    session, events, _ = _load_signal_context(database, signal, request_context=request_context)
    extraction = extract_knowledge_draft(signal, session, events, settings=settings)
    candidate.candidate_type = extraction.knowledge_type
    candidate.scope_hint = {
        'scope_type': extraction.content.get('scope_type', 'repo'),
        'scope_id': extraction.content.get('scope_id', session.repo_id if session else 'global'),
    }
    candidate.quality_score = extraction.quality_score
    candidate.extract_prompt_version = extraction.prompt_version
    candidate.status = 'reviewing'

    knowledge = KnowledgeItem(
        knowledge_id=generate_id('kn'),
        tenant_id=session.tenant_id if session else None,
        team_id=session.team_id if session else None,
        scope_type=extraction.content.get('scope_type', 'repo' if session else 'global'),
        scope_id=extraction.content.get('scope_id', session.repo_id if session else 'global'),
        knowledge_type=extraction.knowledge_type,
        memory_type=extraction.memory_type,
        title=extraction.title,
        content=extraction.content,
        status='draft',
        quality_score=extraction.quality_score,
        confidence_score=extraction.confidence_score,
        freshness_score=extraction.freshness_score,
        created_by=extraction.created_by,
    )
    database.add(knowledge)
    database.flush()

    database.add(
        KnowledgeSourceRef(
            knowledge_id=knowledge.knowledge_id,
            ref_type='session',
            ref_target_id=signal.session_id,
            ref_path=(signal.source_refs.get('file_paths') or [None])[0],
            excerpt_summary=signal.source_refs.get('summary'),
        )
    )

    task.status = 'success'
    task.model_name = extraction.model_name
    task.prompt_version = extraction.prompt_version
    task.result_ref = knowledge.knowledge_id
    task.error_message = None
    signal.status = 'processed'
    append_audit_log(
        database,
        actor_id=actor_id,
        action='knowledge.extract',
        resource_type='knowledge',
        resource_id=knowledge.knowledge_id,
        scope_type=knowledge.scope_type,
        scope_id=knowledge.scope_id,
        detail={'signal_id': signal.signal_id, 'candidate_id': candidate.candidate_id, 'task_id': task.task_id},
    )
    return knowledge


def _find_existing_extract_result(database: Session, signal_id: str) -> tuple[KnowledgeCandidate, ExtractTask] | None:
    candidate = database.scalar(
        select(KnowledgeCandidate).where(KnowledgeCandidate.signal_id == signal_id).order_by(KnowledgeCandidate.created_at.desc())
    )
    if not candidate:
        return None

    task = database.scalar(
        select(ExtractTask).where(ExtractTask.candidate_id == candidate.candidate_id).order_by(ExtractTask.created_at.desc())
    )
    if not task:
        return None
    return candidate, task


def process_extract_task_data(
    task_id: str,
    database: Session,
    *,
    request_context: RequestContext | None = None,
) -> dict:
    current_context = _resolve_request_context(request_context)
    task = _get_scoped_extract_task(database, task_id, request_context=current_context)
    if not task:
        raise ResourceNotFoundError('extract task not found')

    candidate = database.scalar(select(KnowledgeCandidate).where(KnowledgeCandidate.candidate_id == task.candidate_id))
    if not candidate:
        raise ResourceNotFoundError('extract candidate not found')

    signal = database.scalar(select(KnowledgeSignal).where(KnowledgeSignal.signal_id == candidate.signal_id))
    if not signal:
        raise ResourceNotFoundError('signal not found')

    if task.status == 'success':
        return {
            'task_id': task.task_id,
            'candidate_id': task.candidate_id,
            'status': task.status,
            'knowledge_id': task.result_ref,
        }
    if task.status == 'running':
        raise InvalidOperationError('extract task is already running')

    settings = load_settings()
    task.status = 'running'
    database.flush()
    try:
        knowledge = _execute_extract_task(
            database,
            signal=signal,
            candidate=candidate,
            task=task,
            settings=settings,
            actor_id=current_context.user_id or 'system',
            request_context=current_context,
        )
        database.flush()
    except Exception as exc:
        task.status = 'error'
        task.error_message = str(exc)
        database.flush()
        raise

    return {
        'task_id': task.task_id,
        'candidate_id': task.candidate_id,
        'status': task.status,
        'knowledge_id': knowledge.knowledge_id,
    }


def process_pending_extract_tasks_data(
    database: Session,
    *,
    limit: int = 20,
    request_context: RequestContext | None = None,
) -> dict:
    task_ids = [
        task_id
        for task_id in database.scalars(
            select(ExtractTask.task_id)
            .where(ExtractTask.status == 'pending')
            .order_by(ExtractTask.created_at.asc())
            .limit(max(1, min(limit, 100)))
        ).all()
    ]
    processed: list[dict] = []
    for task_id in task_ids:
        processed.append(process_extract_task_data(task_id, database, request_context=request_context))
    return {'processed_count': len(processed), 'items': processed}


def create_extract_task_data(
    payload: ExtractRequest,
    database: Session,
    *,
    request_context: RequestContext | None = None,
) -> dict:
    current_context = _resolve_request_context(request_context)
    settings = load_settings()
    signals = _get_scoped_signal_rows(database, payload.signal_ids, request_context=current_context)
    signal_order = {signal_id: index for index, signal_id in enumerate(payload.signal_ids)}
    signals.sort(key=lambda signal: signal_order.get(signal.signal_id, len(signal_order)))
    if not signals:
        raise ResourceNotFoundError('signals not found')

    created_items: list[dict] = []
    for signal in signals:
        existing = _find_existing_extract_result(database, signal.signal_id)
        if existing and not payload.force:
            candidate, task = existing
            created_items.append(
                {
                    'signal_id': signal.signal_id,
                    'candidate_id': candidate.candidate_id,
                    'task_id': task.task_id,
                    'knowledge_id': task.result_ref,
                    'status': task.status,
                    'deduplicated': True,
                }
            )
            continue

        session, _, _ = _load_signal_context(database, signal, request_context=current_context)
        candidate = _create_candidate_from_signal(database, signal)
        task = _create_extract_task_record(database, candidate, settings=settings)
        append_audit_log(
            database,
            actor_id=current_context.user_id or 'system',
            action='knowledge.extract.enqueue',
            resource_type='extract_task',
            resource_id=task.task_id,
            scope_type='repo',
            scope_id=session.repo_id if session else None,
            detail={'signal_id': signal.signal_id, 'candidate_id': candidate.candidate_id},
        )

        knowledge_id = None
        status = task.status
        if settings.extraction_mode == 'sync':
            processed = process_extract_task_data(task.task_id, database, request_context=request_context)
            knowledge_id = processed['knowledge_id']
            status = processed['status']

        append_audit_log(
            database,
            actor_id=current_context.user_id or 'system',
            action='knowledge.extract.create_task',
            resource_type='extract_task',
            resource_id=task.task_id,
            scope_type='repo',
            scope_id=session.repo_id if session else None,
            detail={'signal_id': signal.signal_id, 'candidate_id': candidate.candidate_id, 'mode': settings.extraction_mode},
        )
        created_items.append(
            {
                'signal_id': signal.signal_id,
                'candidate_id': candidate.candidate_id,
                'task_id': task.task_id,
                'knowledge_id': knowledge_id,
                'status': status,
                'deduplicated': False,
            }
        )

    database.commit()
    return {'items': created_items}


def get_extract_task_data(
    task_id: str,
    database: Session,
    *,
    request_context: RequestContext | None = None,
) -> dict:
    task = _get_scoped_extract_task(database, task_id, request_context=request_context)
    if not task:
        raise ResourceNotFoundError('extract task not found')
    return {
        'task_id': task.task_id,
        'candidate_id': task.candidate_id,
        'status': task.status,
        'model_name': task.model_name,
        'prompt_version': task.prompt_version,
        'result_ref': task.result_ref,
        'error_message': task.error_message,
        'created_at': task.created_at.isoformat(),
        'updated_at': task.updated_at.isoformat(),
    }


def get_knowledge_data(knowledge_id: str, database: Session) -> dict:
    knowledge = _get_scoped_knowledge(database, knowledge_id)
    if not knowledge:
        raise ResourceNotFoundError('knowledge not found')

    return {
        'knowledge_id': knowledge.knowledge_id,
        'title': knowledge.title,
        'knowledge_type': knowledge.knowledge_type,
        'memory_type': knowledge.memory_type,
        'scope_type': knowledge.scope_type,
        'scope_id': knowledge.scope_id,
        'content': knowledge.content,
        'status': knowledge.status,
        'quality_score': float(knowledge.quality_score),
        'confidence_score': float(knowledge.confidence_score),
        'freshness_score': float(knowledge.freshness_score),
        'version': knowledge.version,
        'effective_to': knowledge.effective_to.isoformat() if knowledge.effective_to else None,
        'sources': [
            {
                'ref_type': source.ref_type,
                'ref_target_id': source.ref_target_id,
                'ref_path': source.ref_path,
                'excerpt_summary': source.excerpt_summary,
            }
            for source in knowledge.sources
        ],
    }


def review_knowledge_data(payload: ReviewRequest, database: Session) -> dict:
    knowledge = _get_scoped_knowledge(database, payload.knowledge_id)
    if not knowledge:
        raise ResourceNotFoundError('knowledge not found')

    next_status = {'approve': 'active', 'reject': 'deprecated', 'revise': 'draft'}.get(payload.decision)
    if not next_status:
        raise InvalidOperationError('unsupported decision')

    knowledge.status = next_status
    database.add(
        KnowledgeReview(
            knowledge_id=payload.knowledge_id,
            reviewer_id=payload.reviewer_id,
            decision=payload.decision,
            comment=payload.comment,
        )
    )
    append_audit_log(
        database,
        actor_id=payload.reviewer_id,
        action='knowledge.review',
        resource_type='knowledge',
        resource_id=payload.knowledge_id,
        scope_type=knowledge.scope_type,
        scope_id=knowledge.scope_id,
        detail={'decision': payload.decision, 'comment': payload.comment},
    )
    database.commit()
    return {'knowledge_id': knowledge.knowledge_id, 'status': knowledge.status}


def build_context_pack_data(
    database: Session,
    payload: RetrievalQueryRequest,
    *,
    persist: bool,
    request_context: RequestContext | None = None,
) -> tuple[dict, dict, str]:
    current_context = _resolve_request_context(request_context)
    request_id = generate_id('ret')
    if payload.session_id:
        session = _get_scoped_session(database, payload.session_id, request_context=current_context)
        if not session:
            raise ResourceNotFoundError('session not found')
    if persist:
        database.add(
            RetrievalRequest(
                request_id=request_id,
                session_id=payload.session_id,
                query_text=payload.query,
                query_type=payload.query_type,
                repo_id=payload.repo_id,
                branch_name=payload.branch_name,
                file_paths=payload.file_paths,
                token_budget=payload.token_budget,
            )
        )

    matching_profiles = [
        profile
        for profile in database.scalars(
            apply_config_scope(select(ConfigProfile).where(ConfigProfile.status == 'active'), current_context)
        ).all()
        if scope_matches(profile.scope_type, profile.scope_id, payload.repo_id, payload.file_paths)
    ]
    ranked_profile_rules, profile_vector_backend_name = rank_config_rules(
        matching_profiles,
        payload.query,
        payload.repo_id,
        payload.file_paths,
    )
    selected_profile_rules = select_config_rules(ranked_profile_rules)

    candidate_items = [
        item
        for item in database.scalars(
            apply_knowledge_scope(select(KnowledgeItem).where(KnowledgeItem.status == 'active'), current_context)
        ).all()
        if scope_matches(item.scope_type, item.scope_id, payload.repo_id, payload.file_paths)
    ]

    ranked_items, vector_backend_name = rank_knowledge_items(candidate_items, payload.query, payload.repo_id, payload.file_paths)
    selected_items = ranked_items[:8]

    if persist:
        for rank, item in enumerate(selected_items, start=1):
            database.add(
                RetrievalResult(
                    request_id=request_id,
                    knowledge_id=item['knowledge_id'],
                    recall_channel='hybrid',
                    recall_score=item['lexical_score'],
                    rerank_score=item['score'],
                    selected=True,
                    selected_rank=rank,
                )
            )

    rules = dedupe_ranked_entries([item for item in selected_items if item['knowledge_type'] == 'rule'] + selected_profile_rules)
    cases = [item for item in selected_items if item['knowledge_type'] == 'case']
    procedures = [item for item in selected_items if item['knowledge_type'] == 'procedure']
    ordered_sources = order_context_sources(rules, cases, procedures)

    context_pack = {
        'context_summary': build_context_summary(ordered_sources),
        'rules': rules,
        'cases': cases,
        'procedures': procedures,
        'sources': [
            {
                'knowledge_id': item['knowledge_id'],
                'title': item['title'],
                'knowledge_type': item.get('knowledge_type'),
                'source_type': item['source_type'],
                'scope_type': item.get('scope_type'),
                'scope_id': item.get('scope_id'),
                'score': item.get('score'),
            }
            for item in ordered_sources
        ],
    }
    debug_payload = {
        'request_id': request_id,
        'route_decision': {
            'query_type': payload.query_type,
            'repo_id': payload.repo_id,
            'matched_paths': payload.file_paths,
            'strategy': 'hybrid-retrieval-with-config-scope-and-vector-layer',
            'vector_backend': vector_backend_name,
            'config_vector_backend': profile_vector_backend_name,
        },
        'matching_profiles': [
            {
                'profile_id': profile.profile_id,
                'scope_type': profile.scope_type,
                'scope_id': profile.scope_id,
                'profile_type': profile.profile_type,
                'version': profile.version,
            }
            for profile in matching_profiles
        ],
        'candidate_scores': selected_items,
        'config_rule_scores': ranked_profile_rules[:6],
        'selected_config_rules': selected_profile_rules,
        'selected_sources': ordered_sources,
    }
    return context_pack, debug_payload, request_id


def retrieve_context_pack_data(
    payload: RetrievalQueryRequest,
    database: Session,
    *,
    request_context: RequestContext | None = None,
) -> tuple[dict, str]:
    current_context = _resolve_request_context(request_context)
    context_pack, debug_payload, request_id = build_context_pack_data(
        database,
        payload,
        persist=True,
        request_context=current_context,
    )
    append_audit_log(
        database,
        actor_id=current_context.user_id or 'system',
        action='retrieval.query',
        resource_type='retrieval',
        resource_id=request_id,
        scope_type='repo',
        scope_id=payload.repo_id,
        detail={
            'query_type': payload.query_type,
            'candidate_count': len(debug_payload['candidate_scores']),
            'vector_backend': debug_payload['route_decision']['vector_backend'],
        },
    )
    database.commit()
    return context_pack, request_id


def submit_knowledge_feedback_data(
    payload: FeedbackRequest,
    database: Session,
    *,
    request_context: RequestContext | None = None,
) -> dict:
    current_context = _resolve_request_context(request_context)
    knowledge = _get_scoped_knowledge(database, payload.knowledge_id, request_context=current_context)
    if not knowledge:
        raise ResourceNotFoundError('knowledge not found')

    database.add(
        KnowledgeFeedback(
            knowledge_id=payload.knowledge_id,
            request_id=payload.request_id,
            feedback_type=payload.feedback_type,
            feedback_score=payload.feedback_score,
            feedback_text=payload.feedback_text,
            created_by=payload.created_by,
        )
    )

    normalized_score = max(1, min(payload.feedback_score, 5)) / 5
    knowledge.quality_score = round((float(knowledge.quality_score) * 0.7) + (normalized_score * 0.3), 4)
    if payload.feedback_type in {'wrong', 'stale'}:
        knowledge.freshness_score = round(max(0.1, float(knowledge.freshness_score) - 0.2), 4)

    append_audit_log(
        database,
        actor_id=current_context.user_id or payload.created_by,
        action='feedback.knowledge',
        resource_type='knowledge',
        resource_id=payload.knowledge_id,
        scope_type=knowledge.scope_type,
        scope_id=knowledge.scope_id,
        detail={'feedback_type': payload.feedback_type, 'feedback_score': payload.feedback_score},
    )
    database.commit()
    return {
        'knowledge_id': knowledge.knowledge_id,
        'quality_score': float(knowledge.quality_score),
        'freshness_score': float(knowledge.freshness_score),
    }


def submit_context_pack_feedback_data(
    payload: ContextPackFeedbackRequest,
    database: Session,
    *,
    request_context: RequestContext | None = None,
) -> dict:
    current_context = _resolve_request_context(request_context)
    request = database.scalar(
        apply_retrieval_request_scope(select(RetrievalRequest).where(RetrievalRequest.request_id == payload.request_id), current_context)
    )
    if not request:
        raise ResourceNotFoundError('retrieval request not found')

    database.add(
        ContextPackFeedback(
            request_id=payload.request_id,
            feedback_score=payload.feedback_score,
            relevance_score=payload.relevance_score,
            completeness_score=payload.completeness_score,
            feedback_text=payload.feedback_text,
            created_by=payload.created_by,
        )
    )
    append_audit_log(
        database,
        actor_id=current_context.user_id or payload.created_by,
        action='feedback.context_pack',
        resource_type='retrieval',
        resource_id=payload.request_id,
        scope_type='repo',
        scope_id=request.repo_id,
        detail={
            'feedback_score': payload.feedback_score,
            'relevance_score': payload.relevance_score,
            'completeness_score': payload.completeness_score,
        },
    )
    database.commit()
    return {'request_id': payload.request_id, 'status': 'recorded'}
