"""操作流程写入边界：敏感输入只保留明确的动态秘密引用，历史读取不重写。"""
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.domain.redaction import is_sensitive_key, redact


def validate_public_flow_inputs(steps):
    def reject():
        raise JiejianError(ErrorCode.INPUT_INVALID,'敏感输入只能从前序请求受控提取；账号凭据请在测试账号中准备')

    def sensitive(name):
        return is_sensitive_key(name) or 'csrf' in name.lower()

    def inspect(value, slots, protected=False):
        if isinstance(value,dict):
            if set(value)=={'$slot'}:
                if protected and not getattr(slots.get(value['$slot']),'secret',False):reject()
            else:
                for key,child in value.items():inspect(child,slots,protected or sensitive(key))
        elif isinstance(value,list):
            for child in value:inspect(child,slots,protected)
        elif protected or isinstance(value,str) and redact(value)!=value:
            reject()

    for step in steps:
        request=step.request_template
        slots={slot.slot_id:slot for slot in request.input_slots}
        for field in (*request.query,*request.headers):
            inspect({'$slot':field.slot_id} if field.slot_id else field.literal,slots,sensitive(field.name))
        if request.body.kind.value=='JSON':inspect(request.body.value,slots)
