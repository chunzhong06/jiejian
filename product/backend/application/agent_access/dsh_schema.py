# DSH 工具定义适配；仅转换客户端展示格式，调用前仍执行原始完整 JSON Schema 校验。
from __future__ import annotations

from copy import deepcopy

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


class DshSchemaError(ValueError):
    pass


def project_schema(schema: dict) -> dict:
    """展开本地引用与互斥 nullable 联合；客户端不支持的约束由原始校验器保留。"""
    annotations = {'title', 'description', 'default', 'examples'}
    constraints = {'pattern', 'minLength', 'maxLength', 'minimum', 'maximum', 'exclusiveMinimum',
                   'exclusiveMaximum', 'multipleOf', 'minItems', 'maxItems', 'uniqueItems',
                   'minProperties', 'maxProperties'}
    budget = 4096

    def visit(node, refs=()):
        nonlocal budget
        budget -= 1
        if budget < 0 or len(refs) > 32 or not isinstance(node, dict):
            raise DshSchemaError('工具定义无法安全转换')
        if '$ref' in node:
            ref = node['$ref']
            if not isinstance(ref, str) or not ref.startswith('#/$defs/') or ref in refs:
                raise DshSchemaError('工具引用不受支持')
            target = schema
            for part in ref[2:].split('/'):
                target = target[part.replace('~1', '/').replace('~0', '~')]
            # 引用与同名约束交叠时不能用覆盖合并改变交集语义。
            siblings = {key: value for key, value in node.items() if key != '$ref'}
            if any(key in target and key not in annotations for key in siblings):
                raise DshSchemaError('工具引用存在交叠约束')
            return visit({**target, **siblings}, (*refs, ref))
        result = {}
        notes = []
        for key, value in node.items():
            if key in annotations or key in {'type', 'required', 'enum', 'const'}:
                result[key] = deepcopy(value)
            elif key == 'properties':
                result[key] = {name: visit(item, refs) for name, item in value.items()}
            elif key in {'items', 'additionalProperties'}:
                result[key] = visit(value, refs) if isinstance(value, dict) else value
            elif key in {'anyOf', 'oneOf'}:
                branches = [visit(item, refs) for item in value]
                if key == 'anyOf':
                    types = [item.get('type') for item in branches]
                    if any(not isinstance(item, str) for item in types) or len(set(types)) != len(types) or {'integer', 'number'} <= set(types):
                        raise DshSchemaError('工具联合类型无法等价转换')
                result['oneOf'] = branches
            elif key == '$defs':
                continue
            elif key in constraints:
                notes.append(f'原始校验约束 {key}={value!s}；调用时严格校验。')
            else:
                raise DshSchemaError('工具定义包含未适配的关键字')
        if notes:
            result['description'] = ' '.join([str(result.get('description', '')), *notes]).strip()
        return result

    # 禁止校验器为外部引用访问网络；只允许本地、有界的定义图。
    projected = visit(schema)
    return projected


class DshToolSchemas:
    def __init__(self):
        self.validators: dict[str, Draft202012Validator] = {}

    def adapt(self, payload: dict) -> dict:
        """整批适配成功后替换缓存；未知格式不交付部分工具。"""
        result = deepcopy(payload)
        validators = {}
        try:
            for tool in result.get('result', {}).get('tools', []):
                original = tool['inputSchema']
                Draft202012Validator.check_schema(original)
                tool['inputSchema'] = project_schema(original)
                validators[tool['name']] = Draft202012Validator(original)
        except (SchemaError, KeyError, TypeError, AttributeError):
            raise DshSchemaError('工具定义无法安全转换') from None
        self.validators = validators
        return result

    def validate(self, name, arguments) -> bool:
        validator = self.validators.get(name) if isinstance(name, str) else None
        return validator is not None and validator.is_valid(arguments)

    def validation_issues(self, name, arguments) -> list[dict[str, str]]:
        """只返回原定义声明的字段位置与固定原因，不泄漏输入值、未知键名或异常原文。"""
        validator = self.validators.get(name) if isinstance(name, str) else None
        if validator is None:
            return [{'path':'arguments','message':'工具未注册，请重新读取工具列表'}]
        fields = set()
        def collect(node):
            if isinstance(node, dict):
                fields.update(node.get('properties', {}))
                for value in node.values():
                    collect(value)
            elif isinstance(node, list):
                for value in node:
                    collect(value)
        collect(validator.schema)
        messages = {'pattern':'字段格式不符合原始定义','type':'字段类型不符合原始定义',
            'required':'缺少必填字段','additionalProperties':'包含未声明字段',
            'enum':'值不在允许的枚举中','minLength':'文本长度不足','maxLength':'文本超过长度上限',
            'minItems':'条目数量不足','maxItems':'条目数量超过上限'}
        issues = []
        for error in validator.iter_errors(arguments):
            path = 'arguments'
            for part in list(error.absolute_path)[:16]:
                path += f'[{part}]' if type(part) is int and 0 <= part < 10000 else '.'+(part if isinstance(part,str) and part in fields else '<field>')
            if error.validator == 'required' and isinstance(error.instance, dict):
                missing = next((key for key in error.validator_value if key in fields and key not in error.instance), None)
                if missing:
                    path += '.'+missing
            issues.append({'path':path,'message':messages.get(error.validator,'值或字段组合不符合原始定义')})
            if len(issues) == 8:
                break
        return issues
