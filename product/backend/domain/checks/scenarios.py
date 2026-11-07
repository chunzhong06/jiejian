"""在完整计划上增加准确的场景 occurrence；不读取网络、不生成权限、不裁决结果。"""
import json
from product.backend.domain.checks.plan import CheckCase,CheckPlanGap,ProjectCheckPlan
from product.protocols.checks.execution_request import CaseRole,content_hash
from product.protocols.checks.scenarios import FrozenBusinessScenario,FrozenScenarioInvocation,validate_scenario_cases


def scenario_http_budget(plan,bundle):
    """估算单项受控记录实验的目标请求及恢复份额；不扩大用户授权的总预算。"""
    if plan.scenario is None or any(node.batch is not None for experiment in plan.scenario.document.experiments for node in experiment.invocations):
        return None
    sources={'json_'+source.source_id[4:]:source for source in bundle.proof_sources}
    configurations={action.action_id:action for action in bundle.actions}
    normal=cleanup=0
    for action in plan.actions:
        config=configurations[action.action_id]
        proofs={proof.binding_fingerprint:proof for proof in config.proofs}
        for case in action.cases:
            reads=0
            for requirement in case.proof_requirements:
                proof=proofs[requirement.binding_fingerprint]
                source=sources.get(proof.observer_id)
                if source is None or proof.auxiliary_sources or getattr(source.config,'async_export',None) is not None:
                    return None
                reads+=len({case.subject_test_identity_id,case.resource_owner_test_identity_id,proof.observation_identity_id}-{None})
                if case.subject_test_identity_id is None:reads+=1
            # 实验起点、节点起点、执行后及最终观察；条件在 TARGET 前另读一次。
            phases=2 if config.created_resource is not None else 4+int(case.permission.conditions is not None)
            normal+=reads*phases+len(config.steps)+1
            if config.state_changing:cleanup+=2+reads
    return normal,cleanup


def compile_business_scenario(plan,document,bundle):
    if not plan.actions:
        # 空计划已有准备缺口；没有可归属动作时不制造一个虚构的场景缺口。
        return plan
    fingerprint=content_hash('BusinessScenario',document.model_dump(mode='json'))
    # 场景引用准备好的模板，只执行声明的 occurrence；不在流程外先运行一遍基础写操作。
    cases={action.action_id:[] for action in plan.actions}
    configured={} if bundle is None else {item.action_id:item for item in bundle.actions}
    invocations=[]
    gaps=list(plan.gaps)
    for experiment in sorted(document.experiments,key=lambda item:(item.kind!='NORMAL',item.id)):
        for invocation in experiment.invocations:
            selected=[]
            for item in invocation.items:
                matches=[(action,case) for action in plan.actions for case in action.cases
                    if (case.permission.intent_id,case.permission.revision,case.permission.intent_hash,
                        case.subject_test_identity_id,case.resource_id)==(item.permission.intent_id,item.permission.revision,
                        item.permission.intent_hash,item.subject_identity_id,item.resource_id)]
                if not matches:
                    if plan.actions:
                        gaps.append(CheckPlanGap(action_id=plan.actions[0].action_id,action_revision=plan.actions[0].action_revision,
                            reason='SCENARIO_ITEM_NOT_PREPARED',intent_id=item.permission.intent_id))
                    continue
                # 正常节点承担完整回归，不能复用只覆盖部分效果的同题对照。
                eligible=next((entry for entry in matches if 'ALLOW_REGRESSION' in entry[1].roles),None)
                if eligible is None and matches[0][1].permission.expectation=='ALLOW':
                    gaps.append(CheckPlanGap(action_id=matches[0][0].action_id,action_revision=matches[0][0].action_revision,
                        reason='SCENARIO_FULL_CONTROL_REQUIRED',intent_id=item.permission.intent_id))
                    continue
                selected.append(eligible or matches[0])
            if len(selected)!=len(invocation.items):
                continue
            action_ids={action.action_id for action,_ in selected}
            for item,(_action,case) in zip(invocation.items,selected,strict=True):
                if item.resource_from is None:continue
                producer=next((node for node in experiment.invocations if node.id==item.resource_from),None)
                producer_item=None if producer is None or len(producer.items)!=1 else producer.items[0]
                producer_cases=[] if producer_item is None else [(action,entry) for action in plan.actions for entry in action.cases
                    if (entry.permission.intent_id,entry.permission.revision,entry.permission.intent_hash,
                        entry.subject_test_identity_id,entry.resource_id)==(producer_item.permission.intent_id,
                        producer_item.permission.revision,producer_item.permission.intent_hash,
                        producer_item.subject_identity_id,producer_item.resource_id)]
                if not producer_cases or not any(getattr(configured.get(action.action_id),'created_resource',None) is not None
                        and entry.permission.expectation=='ALLOW' and entry.resource_owner_test_identity_id==case.resource_owner_test_identity_id
                        for action,entry in producer_cases):
                    gaps.append(CheckPlanGap(action_id=selected[0][0].action_id,action_revision=selected[0][0].action_revision,
                        reason='SCENARIO_RESOURCE_PRODUCER_REQUIRED'))
            duplicate_mismatch=any(len({(case.permission.intent_id,case.permission.revision,case.permission.intent_hash)
                for _,case in selected if case.resource_id==resource})>1 for resource in {case.resource_id for _,case in selected})
            if invocation.batch is not None and (len(action_ids)!=1 or duplicate_mismatch):
                gaps.append(CheckPlanGap(action_id=selected[0][0].action_id,action_revision=selected[0][0].action_revision,
                    reason='BATCH_RESOURCE_ASSOCIATION_REQUIRED'))
                continue
            if invocation.batch is not None:
                action_config=configured.get(selected[0][0].action_id)
                try:
                    from product.backend.domain.checks.batch_requests import batch_request
                    batch_request(action_config,invocation,tuple(case for _,case in selected))
                except (ValueError,KeyError,TypeError,AttributeError):
                    gaps.append(CheckPlanGap(action_id=selected[0][0].action_id,action_revision=selected[0][0].action_revision,
                        reason='BATCH_REQUEST_MAPPING_INVALID'))
                    continue
            mixed=any(case.permission.expectation=='DENY' for _,case in selected)
            ids=[]
            for index,(action,base) in enumerate(selected):
                occurrence='occ_'+content_hash('ScenarioOccurrence',dict(scenario=fingerprint,experiment=experiment.id,
                    invocation=invocation.id,index=index))[:32]
                raw=base.model_dump(mode='json',exclude={'case_id'})
                raw['occurrence_id']=occurrence
                if base.permission.expectation=='ALLOW':
                    raw['roles']=[CaseRole.ALLOW_REGRESSION.value]
                if invocation.batch is not None:
                    absent=(invocation.batch.strategy=='ATOMIC' and mixed) or base.permission.expectation=='DENY'
                    raw.update(invocation_kind='BATCH_'+invocation.batch.strategy,batch_effect_expectation='ABSENT' if absent else 'PRESENT')
                identity=content_hash('CheckCase',dict(action_id=action.action_id,revision=action.action_revision,
                    facts={key:value for key,value in raw.items() if key!='roles'}))
                case=CheckCase.model_validate_json(json.dumps(dict(raw,case_id='case_'+identity[:32])))
                cases[action.action_id].append(case)
                ids.append(case.case_id)
            invocations.append(FrozenScenarioInvocation(experiment_id=experiment.id,invocation_id=invocation.id,case_ids=tuple(ids)))
    actions=tuple(action.model_copy(update=dict(cases=tuple(sorted(cases[action.action_id],key=lambda item:item.case_id)),
        twins=())) for action in plan.actions if cases[action.action_id])
    scenario=FrozenBusinessScenario(document=document,fingerprint=fingerprint,invocations=tuple(invocations)) if invocations else None
    if not gaps:
        try:
            validate_scenario_cases(scenario,actions)
        except (ValueError,KeyError):
            gaps.append(CheckPlanGap(action_id=plan.actions[0].action_id,action_revision=plan.actions[0].action_revision,reason='SCENARIO_CONTROL_REQUIRED'))
    payload=plan.model_dump(mode='json',exclude={'plan_fingerprint'})
    payload.update(actions=[action.model_dump(mode='json') for action in actions],gaps=[item.model_dump(mode='json') for item in gaps],
        **({} if scenario is None else dict(scenario=scenario.model_dump(mode='json'))))
    return ProjectCheckPlan.model_validate_json(json.dumps(dict(payload,plan_fingerprint=content_hash('ProjectCheckPlan',payload))))
