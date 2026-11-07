"""在同一 Runner 预算内跟随真实任务，只读取固定状态和最终文件路径。"""
from dataclasses import dataclass
import hashlib
import re
import time
from urllib.parse import quote

from product.backend.domain.errors import JiejianError
from product.backend.domain.verification.async_progress import task_transition
from product.backend.infrastructure.observers.adapters.json_source import strict_json,SourceReadError
from product.backend.infrastructure.observers.records.record_facts import record_value
from product.backend.infrastructure.execution.web.file_entity import FileEntityPolicy
from product.protocols.checks.business_facts import AsyncTaskFact
from product.protocols.preparation.proof_sources import proof_fingerprint


@dataclass(frozen=True)
class AsyncExportResult:
    delivery:object|None=None
    task:AsyncTaskFact|None=None
    reason:str|None=None
    completed:bool=False


def observe_export(owner,*,source,case,action_id,target,claims,cleanup):
    # AFTER 与 EVENTUAL 共用这一次采集；失败或回执未知也不再次派发、轮询或下载。
    key=(case.case_id,source.source_id,source.revision)
    cache=owner._async_exports
    if key in cache:return cache[key]
    cache[key]=AsyncExportResult(reason='ASYNC_EXPORT_UNCONFIRMED')
    config=source.config.async_export
    if target is None or target.status_code!=202:
        return cache[key]
    started=time.monotonic_ns()
    deadline=started+config.timeout_us*1000
    total=0
    task=None
    try:
        dispatched=strict_json(target.body,config.max_response_bytes)
        task_id=record_value(dispatched,config.dispatch_task_path)
        if (not isinstance(task_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',task_id)
                or any(secret and secret in task_id for secret in owner.known_secrets)):
            raise SourceReadError('ASYNC_DISPATCH_TASK_INVALID')
        fingerprint=hashlib.sha256(task_id.encode()).hexdigest()
        previous=None
        subject='anonymous' if case.subject_test_identity_id is None else claims[case.subject_test_identity_id].application_subject_id
        resource_owner=claims[case.resource_owner_test_identity_id].application_subject_id
        with owner.web.identity_session(case.subject_test_identity_id) as identity:
            if owner.web._verify_identity(identity,case.subject_test_identity_id,case,cleanup=cleanup)!='MATCH':
                raise SourceReadError('ASYNC_ACTUAL_IDENTITY_MISMATCH')
            for poll in range(1,config.max_polls+1):
                if owner.cancelled():raise SourceReadError('ASYNC_TASK_CANCELLED')
                if time.monotonic_ns()>=deadline:raise SourceReadError('ASYNC_TASK_OBSERVATION_TIMEOUT')
                path=config.status_path_template.replace('{task_id}',quote(task_id,safe=''))
                response=owner.web.adapter.request('GET',path,case_id=case.case_id,action_id=action_id+'-status',
                    identity_runtime=identity,cleanup_request=cleanup,deadline_ns=deadline)
                total+=len(response.body)
                if total>config.max_response_bytes:raise SourceReadError('ASYNC_TASK_RESPONSE_LIMIT')
                if response.status_code!=200:raise SourceReadError('ASYNC_TASK_HTTP_STATUS')
                data=strict_json(response.body,config.max_response_bytes)
                if (record_value(data,config.task_path)!=task_id
                        or record_value(data,config.resource_path)!=case.resource_id
                        or record_value(data,config.owner_path)!=resource_owner
                        or record_value(data,config.subject_path)!=subject
                        or record_value(data,config.request_nonce_path)!=target.request_nonce):
                    raise SourceReadError('ASYNC_TASK_CORRELATION_CONFLICT')
                raw_state=record_value(data,config.state_path)
                state=config.states.get(raw_state) if isinstance(raw_state,str) else None
                if state is None:raise SourceReadError('ASYNC_TASK_STATE_UNMAPPED')
                terminal=task_transition(previous,task_id,state,task_id)
                task=AsyncTaskFact(task_fingerprint=fingerprint,mapping_fingerprint=proof_fingerprint(config),
                    dispatch_request_digest=target.request_digest,state=state,subject_identity_id=case.subject_test_identity_id,
                    owner_identity_id=case.resource_owner_test_identity_id,resource_id=case.resource_id,correlated=True,polls_used=poll)
                previous=state
                if terminal:
                    if state!='SUCCESS':raise SourceReadError('ASYNC_TASK_'+state)
                    # 状态响应中的 URL、长度、摘要均不作为文件依据；固定模板和实际完整实体单独采集。
                    delivery=owner.web.adapter.request('GET',config.file_path_template.replace('{task_id}',quote(task_id,safe='')),
                        case_id=case.case_id,action_id=action_id+'-artifact',identity_runtime=identity,cleanup_request=cleanup,
                        deadline_ns=deadline,entity_policy=FileEntityPolicy(max_bytes=owner.bundle.target.max_response_bytes))
                    if time.monotonic_ns()>=deadline:raise SourceReadError('ASYNC_TASK_OBSERVATION_TIMEOUT')
                    cache[key]=AsyncExportResult(delivery=delivery,task=task,completed=True)
                    return cache[key]
                until=min(deadline,time.monotonic_ns()+min(config.poll_interval_us*(2**min(poll-1,3)),1_000_000)*1000)
                while time.monotonic_ns()<until:
                    if owner.cancelled():raise SourceReadError('ASYNC_TASK_CANCELLED')
                    time.sleep(max(0,min(.05,(until-time.monotonic_ns())/1_000_000_000)))
            raise SourceReadError('ASYNC_TASK_OBSERVATION_TIMEOUT')
    except (SourceReadError,JiejianError,ValueError) as error:
        reason=error.code if isinstance(error,(SourceReadError,JiejianError)) else 'ASYNC_TASK_STATE_CONFLICT'
        cache[key]=AsyncExportResult(task=task,reason=reason)
        return cache[key]
