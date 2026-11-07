"""从已冻结的单项模板构造一次批量请求，保持输入顺序和准确的资源关联。"""
from copy import deepcopy
import json
from product.protocols.web.request import HttpRequestTemplate


def batch_request(action,invocation,cases):
    if action is None or invocation.batch is None or not cases:
        raise ValueError('batch configuration missing')
    if any(proof.effect_kind not in {'STATE_MUTATION','DATA_DISCLOSURE'} for proof in action.proofs):
        raise ValueError('this effect has no per-item batch proof')
    if any(proof.effect_kind=='DATA_DISCLOSURE' for proof in action.proofs) and (
        invocation.batch.response_items_path is None or invocation.batch.response_resource_field is None):
        raise ValueError('batch disclosure requires explicit per-item response correlation')
    target=next(step for step in action.steps if step.purpose=='TARGET')
    request=target.request
    slots=[slot for slot in request.input_slots if slot.source.value=='CASE_RESOURCE_ID']
    if request.body.kind.value!='JSON' or len(slots)!=1 or slots[0].consumer.value!='JSON_BODY':
        raise ValueError('batch input must use its one declared JSON resource slot')
    value=deepcopy(request.body.value)
    parent=value
    for part in invocation.batch.array_path[:-1]:
        parent=parent[part]
    key=invocation.batch.array_path[-1]
    existing=parent[key]
    if not isinstance(existing,list) or len(existing)!=1:
        raise ValueError('batch array path must identify the adopted one-item input')
    slot_id=slots[0].slot_id
    def replace(item,resource):
        if isinstance(item,dict):
            if set(item)=={'$slot'} and item['$slot']==slot_id:
                return resource,1
            result,count={},0
            for name,child in item.items():
                result[name],found=replace(child,resource)
                count+=found
            return result,count
        if isinstance(item,list):
            result,count=[],0
            for child in item:
                rendered,found=replace(child,resource)
                result.append(rendered)
                count+=found
            return result,count
        return item,0
    items=[]
    for case in cases:
        item,count=replace(existing[0],case.resource_id)
        if count!=1:
            raise ValueError('batch item must contain its exact declared resource slot')
        items.append(item)
    parent[key]=items
    raw=request.model_dump(mode='json')
    raw['body']['value']=value
    raw['input_slots']=[slot for slot in raw['input_slots'] if slot['slot_id']!=slot_id]
    return HttpRequestTemplate.model_validate_json(json.dumps(raw))
