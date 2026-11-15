"""从两份冻结包比较原题请求条件，不依赖当前流程、展示名称或LLM判断。"""
from __future__ import annotations

import re

from product.protocols.codec import content_hash


def _challenge(request, bundle, case_id):
    action,case=next((action,case) for action in request.actions for case in action.cases if case.case_id==case_id)
    configured=next(item for item in bundle.actions if item.action_id==action.action_id)
    if configured.flow_id!=case.execution.flow_id or not configured.steps or configured.steps[-1].purpose!='TARGET':
        raise ValueError('frozen challenge unavailable')
    indexes={step.step_id:index for index,step in enumerate(configured.steps)}

    def template(value):
        slots={slot.slot_id:slot for slot in value.input_slots}

        def slot_value(key):
            slot=slots[key]
            if slot.source=='FIXED_LITERAL':
                return {'literal':slot.literal}
            # 槽名和录制步骤ID可变化，业务来源、提取位置及实际消费位置必须保持。
            producer=indexes[slot.producer_step_id] if slot.producer_step_id else slot.producer_step
            return {'slot':{'source':slot.source,'type':slot.value_type,'secret':slot.secret,
                'producer':producer,'path':slot.source_path,'secret_ref':slot.secret_ref}}

        def node(value):
            if isinstance(value,dict):
                if set(value)=={'$slot'}:return slot_value(value['$slot'])
                return {'object':[(key,node(value[key])) for key in sorted(value)]}
            if isinstance(value,list):return {'array':[node(item) for item in value]}
            return {'literal':value}

        def parameters(values,*,headers=False):
            records=[(item.name.lower() if headers else item.name,
                {'literal':item.literal} if item.slot_id is None else slot_value(item.slot_id)) for item in values]
            # Query/Form可能含有有意义的重复次序，公开头名称则按HTTP的不区分大小写比较。
            return sorted(records,key=lambda item:item[0]) if headers else records

        path=[slot_value(part[1:-1]) if part.startswith('{') else {'literal':part}
            for part in re.split(r'(\{[A-Za-z][A-Za-z0-9_.:-]*\})',value.path) if part]
        body=value.body
        if body.kind=='JSON':payload=node(body.value)
        elif body.kind=='FORM_URLENCODED':payload=parameters(body.fields)
        elif body.kind=='MULTIPART':
            payload=[{'name':part.name,'filename':part.filename,'content_type':part.content_type,
                'value':slot_value(part.slot_id) if part.slot_id else {'fixture':part.fixture_artifact_id} if part.fixture_artifact_id else {'literal':part.literal}}
                for part in body.parts]
        else:payload=None
        return dict(method=value.method,path=path,query=parameters(value.query),headers=parameters(value.headers,headers=True),
            body_kind=body.kind,body=payload)

    # SETUP与TARGET沿用Case身份；保留请求、顺序与依赖，只忽略未被消费的响应提取器。
    steps=[dict(purpose=step.purpose,
        dependencies=sorted(indexes[key] for key in step.depends_on_step_ids),request=template(step.request))
        for step in configured.steps]
    scenario=getattr(request,'scenario',None)
    return content_hash('RepairRequestChallenge',dict(steps=steps,scenario=None if scenario is None else scenario.fingerprint))


def repair_challenge_reason(*,original_request,original_bundle,request,bundle,source_case_id,case_id):
    """旧Run已有完整模板即可核对；缺原模板必须保留未完成，不能用本次请求回填原题。"""
    if original_request is None or original_bundle is None:
        return 'REPAIR_CHALLENGE_UNAVAILABLE'
    try:
        before=_challenge(original_request,original_bundle,source_case_id)
        after=_challenge(request,bundle,case_id)
    except (KeyError,ValueError,StopIteration,AttributeError):
        return 'REPAIR_CHALLENGE_UNAVAILABLE'
    return None if before==after else 'REPAIR_CHALLENGE_CHANGED'
