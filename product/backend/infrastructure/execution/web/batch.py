"""一次真实批量调用的临时回执分配；不重复发送，也不持久化响应正文。"""
from dataclasses import replace
import json
from product.backend.domain.checks.batch_requests import batch_request
from product.backend.domain.errors import JiejianError
from product.protocols.web.response import _read_json_path


def execute_batch(web,action,case,group,*,verify_identity,before_target):
    if 'error' in group:
        raise JiejianError(group['error'],'本次批量请求没有可复用的完整回执')
    if 'result' not in group:
        invocation,cases=group['invocation'],group['cases']
        request=batch_request(action,invocation,cases)
        steps=tuple(step.model_copy(update={'request':request}) if step.purpose=='TARGET' else step for step in action.steps)
        def check(actual):
            if before_target is not None:
                before_target(actual)
            group['before_others'](actual)
        try:
            group['result']=web.execute_steps(action.action_id,steps,case,verify_identity=verify_identity,before_target=check)
        except JiejianError as error:
            group['error']=error.code
            raise
        finally:
            if web.target_attempted(case.case_id):
                for member in cases:
                    web._executed.add(member.case_id)
                    web._actual_identities[member.case_id]=web.actual_identity_status(case.case_id)
                    web._target_receipts[member.case_id]=web.target_request(case.case_id)
        execution,response,identity=group['result']
        for member in cases:
            web._target_responses[member.case_id]=_item_response(response,invocation.batch,member)
    execution,_response,identity=group['result']
    return execution,web._target_responses[case.case_id],identity


def _item_response(response,batch,case):
    if batch.response_items_path is None or response.status_code in {401,403}:
        return response
    found,rows=_read_json_path(response.data,batch.response_items_path)
    if not found or not isinstance(rows,list) or len(rows)>32 or any(not isinstance(item,dict) for item in rows):
        return replace(response,data={},body=b'{}')
    identifiers=[item.get(batch.response_resource_field) for item in rows]
    if any(not isinstance(key,str) for key in identifiers) or len(set(identifiers))!=len(identifiers):
        return replace(response,data={},body=b'{}')
    selected=[item for item in rows if item[batch.response_resource_field]==case.resource_id]
    if not selected:
        return replace(response,data={},body=b'{}',batch_item_absent=True)
    value=selected[0]
    return replace(response,data=value,body=json.dumps(value,ensure_ascii=False,separators=(',',':')).encode())
