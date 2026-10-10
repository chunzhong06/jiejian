# 从当前采用来源读取同一请求的显式事件；业务事实与 Verdict 继续由原证明链决定。
import json
from product.backend.core.errors import JiejianError
from product.backend.core.verification.trace import ExecutionTrace,TraceEvent
from product.backend.infra.observers.records.record_source import read_record_source
from product.backend.infra.observers.adapters.json_source import SourceReadError
from product.backend.infra.observers.records.source_contracts import audit_source_contract


def managed_execution_trace(owner,action,case):
    target=owner.web.target_response(case.case_id)
    sources={source.config.collection:source for proof in action.proofs
        if (source:=owner._json_sources.get(proof.observer_id)) is not None}
    if not sources or target is None:return None
    events,seen,reasons=[],set(),set()
    # 此通道未声明独立 Trace 身份命名空间，计划主体保持冻结账号 ID；应用主体只作为事件事实。
    subject=case.subject_test_identity_id
    for source in sources.values():
        try:
            if audit_source_contract(owner.var_dir,owner.bundle.runtime_reference,source.config)!=source.contract:
                raise SourceReadError('RECORD_PROVIDER_UNAVAILABLE')
            log=read_record_source(owner.var_dir,owner.bundle.runtime_reference,source.config,case.resource_id,
                request_nonce=target.request_nonce,trace=True,cancelled=owner.cancelled)
            generations={snapshot.generation for (case_id,_),snapshot in owner._json_histories.items()
                if case_id==case.case_id and snapshot.collection==source.config.collection and snapshot.resource_id==case.resource_id}
            if log.request_digest!=target.request_digest or generations!={log.generation}:
                raise SourceReadError('TRACE_CORRELATION_INVALID')
            if log.scope_state!='COMPLETE':reasons.add('TRACE_SOURCE_INCOMPLETE')
            if not log.events:reasons.add('TRACE_EVENTS_UNAVAILABLE')
            elif log.events[-1].semantic_key!='response_prepared':reasons.add('TRACE_SOURCE_INCOMPLETE')
            for item in log.events:
                if item.event_id in seen:raise ValueError('duplicate trace event')
                seen.add(item.event_id)
                # 应用记录的身份不覆盖已独立核对的账号；提交事件已由记录服务校验操作归属。
                event=TraceEvent.model_validate_json(json.dumps(dict(event_id=item.event_id,
                    parent_event_ids=[item.parent_event_id] if item.parent_event_id else [],case_id=case.case_id,
                    action_id=action.action_id,resource_ids=[case.resource_id],kind=item.kind,semantic_key=item.semantic_key,
                    subject_id=item.subject_id,authorization_decision=item.authorization_decision,
                    source_component=item.source_component,source_location=item.source_location,
                    correlation_kind='EXPLICIT_PARENT' if item.parent_event_id else 'CASE_MARKER',recorded_at_us=item.recorded_at_us)))
                if any(secret and secret in event.model_dump_json() for secret in owner.known_secrets):raise ValueError('secret trace input')
                events.append(event)
        except (SourceReadError,ValueError,JiejianError,OSError):
            reasons.add('TRACE_SOURCE_INCOMPLETE')
    try:
        return ExecutionTrace(case_id=case.case_id,action_id=action.action_id,planned_subject_id=subject,
            events=tuple(events),complete=not reasons,reason_codes=tuple(sorted(reasons)))
    except ValueError:
        return ExecutionTrace(case_id=case.case_id,action_id=action.action_id,planned_subject_id=subject,
            events=(),complete=False,reason_codes=('TRACE_GRAPH_INVALID',))
