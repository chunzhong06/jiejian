"""在一个 CHECK attempt 内执行业务实验；逐动作采证，实验结束后按逆序恢复。"""
from product.backend.domain.errors import JiejianError
from product.backend.domain.verification.checks import resolved_control_verdict
from product.protocols.checks.conditions import collected_conditions_status


def execute_business_scenario(owner,configured,results,evidence,started):
    scenario=owner.request.scenario
    by_case={case.case_id:(action,case) for action in owner.request.actions for case in action.cases}
    groups={(item.experiment_id,item.invocation_id):item for item in scenario.invocations}
    planned=sum(len(action.cases) for action in owner.request.actions)
    for experiment in sorted(scenario.document.experiments,key=lambda item:(item.kind!='NORMAL',item.id)):
        order=[key for invocation in experiment.invocations for key in groups[experiment.id,invocation.id].case_ids]
        initial={}
        pending={}
        exports={}
        restored_resources={}
        items={key:item for node in experiment.invocations
            for key,item in zip(groups[experiment.id,node.id].case_ids,node.items,strict=True)}
        # 所有相关投影在实验开始前取得，用于核对最终恢复；每步执行前仍另外重新采集。
        if owner._stopped is None:
            for key in order:
                action,case=by_case[key]
                if items[key].resource_from is not None or configured[action.action_id].created_resource is not None:continue
                try:
                    values=owner._observe(configured[action.action_id],case,'BASELINE',baseline=False)
                    initial[key]=tuple(item.baseline_projection for item in values)
                    # 实验起点只用于最终恢复；节点效果必须从该节点真正执行前重新建窗。
                    owner.observers.restart_case_baseline(key)
                except JiejianError as error:
                    owner._stop(error.code,'BASELINE')
                    break
        for invocation in experiment.invocations:
            ids=groups[experiment.id,invocation.id].case_ids
            for key in ids:
                item=items[key]
                if item.resource_from is None or owner._stopped is not None:continue
                produced=exports.get(item.resource_from)
                if produced is None:
                    owner._stop('SCENARIO_RESOURCE_UNCONFIRMED','PREPARING')
                    continue
                from product.protocols.checks.check_result import ScenarioResourceBinding
                producer_id,resource_id=produced
                action,template=by_case[key]
                binding=ScenarioResourceBinding(producer_case_id=producer_id,resource_id=resource_id)
                case=template.bind_resource(resource_id,producer_id)
                by_case[key]=(action,case)
                owner._scenario_bindings[key]=binding
                try:
                    values=owner._observe(configured[action.action_id],case,'BASELINE',baseline=False)
                    initial[key]=tuple(value.baseline_projection for value in values)
                    owner.observers.restart_case_baseline(key)
                except JiejianError as error:
                    # 绑定后读不到对象也要进入统一收尾，不能遗留前一步已创建的数据。
                    owner._stop(error.code,'BASELINE')
            members=tuple(by_case[key][1] for key in ids)
            if owner.cancelled() and owner._stopped is None:
                owner._stop('EXEC_CANCELLED','EXECUTION')
            if owner.clock()-started>=owner.bundle.budget.max_duration_us and owner._stopped is None:
                owner._stop('EXEC_TIMEOUT','EXECUTION')
            before={}
            extra={key:[] for key in ids}
            if invocation.batch is not None and owner._stopped is None:
                try:
                    for key in ids:
                        action,case=by_case[key]
                        before[key]=owner._observe(configured[action.action_id],case,'BASELINE',baseline=False)
                except JiejianError as error:
                    owner._stop(error.code,'BASELINE')
                def before_others(actual):
                    if actual!='MATCH':
                        raise JiejianError('PERMISSION_CONDITION_UNKNOWN','批量调用的实际主体尚未确认')
                    for key in ids[1:]:
                        action,case=by_case[key]
                        if case.permission.conditions is None:
                            continue
                        values=owner._observe(configured[action.action_id],case,'BEFORE',baseline=True)
                        extra[key].extend(item.observation for item in values)
                        if tuple(item.baseline_projection for item in values)!=tuple(item.baseline_projection for item in before[key]):
                            raise JiejianError('BASELINE_INTEGRITY_INVALID','批量准备步骤改变了检查对象')
                        status=collected_conditions_status(case.permission.conditions,owner._condition_facts(case))
                        if status!='MATCH':
                            raise JiejianError('PERMISSION_CONDITION_'+status,'批量项不满足准确的权限条件')
                group=dict(invocation=invocation,cases=members,before_others=before_others)
                for key in ids:
                    owner.web._batch_groups[key]=group
            for key in ids:
                action,case=by_case[key]
                config=configured[action.action_id]
                owner.progress('EXECUTING',len(results)+len(pending),planned)
                value=owner._case(action,config,case,None,defer_recovery=True,preobserved=before.get(key))
                value['observations'].extend(extra[key])
                if owner._stopped is not None and owner.web.target_attempted(key) and not value['baseline'] and key in before:
                    # 共享请求在另一项处理时失联，仍核对本项的原 nonce；不重发批量请求。
                    value['baseline']=all(item.baseline_projection is not None for item in before[key])
                    value['identity']=owner.web.actual_identity_status(key)
                    try:after=owner._observe(config,case,'AFTER',baseline=value['baseline'],cleanup=True)
                    except JiejianError:
                        after=()
                        owner._cleanup_issues.append('SCENARIO_AFTER_UNVERIFIED')
                    value['observations'].extend(item.observation for item in (*before[key],*after))
                    value['correlated']=any(item.observation.correlated for item in after)
                pending[key]=value
                if config.created_resource is not None:
                    initial[key]=owner._creation_baselines.get(key,())
                    entries=[owner.observers._creation_histories.get((key,proof.binding_fingerprint)) for proof in config.proofs]
                    ids_created={event.member.resource_id for entry in entries if entry for event in entry['created']}
                    from product.backend.infrastructure.observers.checks.creation_evidence import response_resource
                    response_id=response_resource(config,owner.web.target_response(key))
                    if (case.permission.expectation=='ALLOW' and value['execution']=='ACCEPTED'
                            and entries and all(entry is not None and entry['closed'] for entry in entries)
                            and len(ids_created)==1 and response_id in ids_created):
                        exports[invocation.id]=(key,response_id)
        recovery_failed=False
        recovered_groups=set()
        by_invocation={key:group.invocation_id for group in scenario.invocations if group.experiment_id==experiment.id for key in group.case_ids}
        for key in reversed(order):
            action,case=by_case[key]
            config=configured[action.action_id]
            if not config.state_changing or not owner.web.target_attempted(key):
                continue
            group_key=(by_invocation[key],action.action_id,case.resource_id,case.resource_owner_test_identity_id)
            if group_key in recovered_groups:continue
            recovered_groups.add(group_key)
            aliases=[other for other in order if (by_invocation[other],by_case[other][0].action_id,by_case[other][1].resource_id,
                by_case[other][1].resource_owner_test_identity_id)==group_key]
            try:
                # 一个批量请求里的重复资源共享一次恢复，不因输入重复再发恢复请求。
                for other in aliases:owner.scenario_journal.record(other,'RECOVERY_INTENT')
                if config.created_resource is not None:
                    from product.backend.infrastructure.execution.creation_check import recover_created
                    entries=[owner.observers._creation_histories[(key,proof.binding_fingerprint)] for proof in config.proofs]
                    recover_created(owner,config,case,entries,restored_resources=restored_resources)
                else:owner._recover_request(config,case)
                if items[key].resource_from is not None or config.created_resource is not None:
                    restored=owner._observe(config,case,'RECOVERY',baseline=pending[key]['baseline'],cleanup=True)
                    pending[key]['observations'].extend(value.observation for value in restored)
                    projection=tuple(value.baseline_projection for value in restored)
                    pending[key]['recovered']=bool(projection) and all(value is not None for value in projection) and projection==initial.get(key)
                    if not pending[key]['recovered']:raise JiejianError('SCENARIO_RECOVERY_UNVERIFIED','场景数据尚未恢复')
                    pending[key]['_recovery_checked']=True
                    owner.scenario_journal.record(key,'RECOVERED')
                    if items[key].resource_from is not None:
                        views=[view for (case_id,_),view in owner.observers._last_record_views.items() if case_id==key]
                        if views:restored_resources[case.resource_id]=views[-1].snapshot
            except (JiejianError,ValueError) as error:
                if isinstance(error,JiejianError):owner._cleanup_issues.append(error.code)
                recovery_failed=True
                owner._cleanup_issues.append('SCENARIO_RECOVERY_UNVERIFIED')
                # 未确认恢复不靠重复请求重试，也不继续依赖它的逆操作。
                break
        for key in order:
            action,case=by_case[key]
            config=configured[action.action_id]
            value=pending[key]
            checked=value.pop('_recovery_checked',False)
            if config.state_changing and owner.web.target_attempted(key) and not checked:
                try:restored=owner._observe(config,case,'RECOVERY',baseline=value['baseline'],cleanup=True)
                except JiejianError:
                    restored=()
                    recovery_failed=True
                value['observations'].extend(item.observation for item in restored)
                projection=tuple(item.baseline_projection for item in restored)
                value['recovered']=not recovery_failed and key in initial and all(item is not None for item in projection) and projection==initial[key]
                if not value['recovered']:
                    owner._cleanup_issues.append('SCENARIO_RECOVERY_UNVERIFIED')
                    owner._stop('SCENARIO_RECOVERY_UNVERIFIED','RECOVERY')
                else:
                    owner.scenario_journal.record(key,'RECOVERED')
            allow=resolved_control_verdict(owner.request,action,case,results)
            result,document=owner._complete_case(action,config,case,allow,**value)
            results[key]=result
            evidence.append(document)
    owner.progress('EXECUTING',len(results),planned)
