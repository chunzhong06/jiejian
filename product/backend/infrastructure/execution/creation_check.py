# 运行期对象检查：TARGET只执行一次；独立创建记录决定对象关联，恢复不使用录制样本编号。
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.domain.verification.checks import CheckDecisionInput, evaluate_check_case, project_check_effect_facts
from product.backend.infrastructure.observers.checks.creation_evidence import collection_digest, response_resource
from product.backend.infrastructure.observers.checks.sealed_facts import finalize_facts
from product.backend.infrastructure.observers.records.record_source import read_record_source
from product.backend.infrastructure.observers.adapters.json_source import SourceReadError
from product.protocols.checks.check_result import CheckCaseOutcome, CheckCaseResult, seal_check_evidence


def execute_creation_case(executor, action, configured, case, allow_verdict):
    web, observers = executor.web, executor.observers
    execution, status, identity = 'UNKNOWN', None, 'UNKNOWN'
    baseline, recovered, correlated = False, False, False
    observations, original = [], None

    def observe(phase, cleanup=False):
        values=executor._observe(configured,case,phase,baseline=baseline,cleanup=cleanup)
        observations.extend(item.observation for item in values)
        return values

    def before_target(actual_identity):
        nonlocal baseline, original
        if actual_identity!='MATCH':
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'创建前未确认实际操作账号')
        # SETUP执行后再建窗，防止准备步骤产生的对象被归到TARGET。
        values=observe('BASELINE')
        original=tuple(item.baseline_projection for item in values)
        baseline=bool(values) and all(value is not None for value in original)
        if not baseline:
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'新对象的独立观察基线尚未就绪')

    if executor._stopped is None:
        try:
            fact,response,identity=web.execute_flow(configured,case,verify_identity=True,before_target=before_target)
            execution,status=fact.outcome.value,response.status_code
        except JiejianError as error:
            identity=web.actual_identity_status(case.case_id)
            executor._stop(error.code,'EXECUTION')
        finally:
            if web.target_attempted(case.case_id):
                # 失败、取消、403和无响应都继续只读取证；异常状态不能掩盖已经提交的禁止创建。
                after=observe('AFTER',cleanup=True)
                correlated=any(item.observation.correlated for item in after)
                entries=[observers._creation_histories.get((case.case_id,proof.binding_fingerprint)) for proof in configured.proofs]
                closed=all(entry is not None and entry['closed'] for entry in entries)
                ids={event.member.resource_id for entry in entries if entry for event in entry['created']}
                actual=response_resource(configured,web.target_response(case.case_id))
                if execution=='ACCEPTED' and (not closed or len(ids)!=1 or actual not in ids or status==202):
                    execution='UNKNOWN'
                try:
                    if not closed:
                        raise ValueError('creation window is not closed')
                    recover_created(executor,configured,case,entries)
                    restored=observe('RECOVERY',cleanup=True)
                    recovered=baseline and tuple(item.baseline_projection for item in restored)==original
                except (JiejianError,SourceReadError,ValueError):
                    recovered=False
                if not recovered:
                    executor._cleanup_issues.append('CREATION_RECOVERY_UNVERIFIED')
                    executor._stop('CREATION_RECOVERY_UNVERIFIED','RECOVERY')
    observations,facts,references=finalize_facts(tuple(observations),observers._evidence_sources)
    outcome=CheckCaseOutcome(execution_outcome=execution,http_status=status,actual_identity_status=identity,
        baseline_trusted=baseline,recovery_verified=recovered,run_correlated=correlated,resource_correlated=correlated)
    decision=evaluate_check_case(CheckDecisionInput(case=case,execution=execution,actual_identity=identity,
        run_correlated=correlated,resource_correlated=correlated,baseline_trusted=baseline,
        recovery_verified=recovered,allow_control_verdict=allow_verdict,effects=project_check_effect_facts(case,observations)))
    document=seal_check_evidence(run_id=executor.input.run_id,job_id=executor.input.job_id,
        attempt=executor.input.attempt,action_id=action.action_id,action_revision=action.action_revision,
        request_hash=executor.input.request_hash,config_hash=executor.input.config_hash,case=case,outcome=outcome,
        observations=observations,business_facts=facts,fact_references=references)
    return CheckCaseResult(case_id=case.case_id,action_id=action.action_id,verdict=decision.verdict,
        reason_codes=decision.reason_codes,evidence_ids=(document.evidence_id,),outcome=outcome),document


def recover_created(executor, action, case, entries):
    """只恢复同一请求独立证明的新对象；无创建不发删除请求，集合或对象并发变化即停。"""
    # 同动作的多个创建证明须覆盖同一集合；独立取证重复，恢复只执行一次。
    source=executor.observers._json_sources[action.proofs[0].observer_id]
    entry=entries[0]
    if any(other['before']!=entry['before'] or other['last']!=entry['last'] or other['created']!=entry['created'] for other in entries):
        raise ValueError('creation sources disagree')
    expected=entry['last']
    for event in entry['created']:
        current=read_record_source(executor.observers.var_dir,executor.bundle.runtime.reference,source.config,
            case.resource_id,request_nonce=executor.web.target_request(case.case_id)[0])
        if (current.generation!=expected.generation or current.watermark!=expected.watermark
                or current.foreign_mutations or collection_digest(current)!=collection_digest(expected)):
            raise ValueError('creation resource changed before recovery')
        member=next((item for item in current.members if item.resource_id==event.member.resource_id),None)
        if member is None:
            continue
        if member.incarnation!=event.member.incarnation:
            raise ValueError('creation incarnation changed')
        recovery=action.recovery
        if executor.web.verify_identity(recovery.source_subject_identity_id,case,cleanup=True)!='MATCH':
            raise ValueError('recovery identity mismatch')
        executor.web.request(recovery.request,case=case,action_id='creation-recovery',identity_id=recovery.source_subject_identity_id,
            resource_id=member.resource_id,cleanup=True)
        restored=read_record_source(executor.observers.var_dir,executor.bundle.runtime.reference,source.config,
            case.resource_id,request_nonce=executor.web.target_request(case.case_id)[0])
        remaining=tuple(item for item in expected.members if item.resource_id!=member.resource_id)
        if restored.generation!=expected.generation or restored.members!=remaining:
            raise ValueError('creation recovery did not restore exact collection')
        expected=restored
