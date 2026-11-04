"""有界读取外部接口资料并归一结构；所有参数值和响应正文均不进入来源资产。"""
import hashlib
import re
from pydantic import ValidationError
from urllib.parse import parse_qsl, urlsplit

from product.backend.domain.errors import ErrorCode, JiejianError
from product.protocols.codec import decode_json, encode_json
from product.protocols.preparation.api_source import SourceParameter, SourceRequest

_METHODS = {'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'}
_SENSITIVE = re.compile(r'password|passwd|secret|token|cookie|authorization|api[_-]?key|csrf|xsrf', re.I)


def source_error(message):
    raise JiejianError(ErrorCode.INPUT_INVALID, message)


def normalize_source(raw: str, kind: str):
    try:
        return _normalize_source(raw, kind)
    except (ValidationError, UnicodeError, ValueError, TypeError):
        source_error('来源中的请求或字段结构无效，请核对声明格式与预算')


def _normalize_source(raw: str, kind: str):
    try:
        document = decode_json(raw, limit=4_194_304)
    except (ValueError, TypeError):
        source_error('请选择不超过4MiB、没有重复键的JSON对象')
    if not isinstance(document, dict):
        source_error('来源根节点必须是JSON对象')
    count, stack = 0, [(document, 0)]
    references, scripts = False, False
    while stack:
        value, depth = stack.pop()
        count += 1
        if count > 40000 or depth > 32:
            source_error('来源结构超过条目或嵌套预算')
        if isinstance(value, str) and len(value) > 262144:
            source_error('来源包含过长文本，请导出较小范围')
        if isinstance(value, dict):
            if '$ref' in value:
                references = True
                if not isinstance(value['$ref'], str) or not value['$ref'].startswith('#/'):
                    source_error('外部引用尚未接受，请提供本地展开的文档；不会抓取远程地址')
            scripts = scripts or 'event' in value
            stack.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            stack.extend((child, depth + 1) for child in value)

    requests, warnings = [], ['参数值、认证值、请求正文和响应正文未导入，请在场景中核对测试数据。']
    if references:
        warnings.append('只展开文档内的本地引用；外部引用不会读取。')
    if scripts:
        warnings.append('集合脚本未执行；脚本产生的变量需要改为显式准备步骤。')

    def resolved(value, seen=()):
        if not isinstance(value, dict):
            source_error('接口结构定义必须是对象')
        reference = value.get('$ref')
        if reference is None:
            return value
        if reference in seen or len(seen) >= 16:
            source_error('本地引用循环或层级过深，请展开需要的接口范围')
        target = document
        for part in reference[2:].split('/'):
            part = part.replace('~1','/').replace('~0','~')
            if not isinstance(target, dict) or part not in target:
                source_error('本地引用不存在，请核对文档')
            target = target[part]
        return resolved(target, (*seen,reference)) | {key:item for key,item in value.items() if key != '$ref'}

    def named(name, location, required=False):
        if not isinstance(name, str) or not 1 <= len(name) <= 128 or any(ord(char)<32 for char in name):
            source_error('字段名称无效或过长')
        return SourceParameter(name=name, location=location, required=required, sensitive=bool(_SENSITIVE.search(name)))

    def captured_fields(request):
        parameters=[]
        headers=request.get('headers',request.get('header',[]))
        if not isinstance(headers,list):
            source_error('请求头结构必须是列表')
        for header in headers:
            if not isinstance(header,dict):
                source_error('请求头条目必须是对象')
            parameters.append(named(header.get('name',header.get('key')), 'HEADER'))
        body=request.get('postData',request.get('body',{}))
        if not isinstance(body,dict):
            source_error('请求正文结构必须是对象')
        fields=body.get('params',body.get('urlencoded',body.get('formdata',[])))
        if not isinstance(fields,list):
            source_error('表单字段结构必须是列表')
        for field in fields:
            if not isinstance(field,dict):
                source_error('表单字段必须是对象')
            parameters.append(named(field.get('name',field.get('key')), 'BODY'))
        return parameters

    def add(method, address, label, pointer, parameters=()):
        if not isinstance(method, str) or method.upper() not in _METHODS:
            source_error('来源包含不支持的请求方法')
        if not isinstance(address, str) or '{{' in address:
            source_error('请求地址含未解析变量，请先在原工具展开地址变量')
        parsed = urlsplit(address)
        if parsed.username is not None or parsed.password is not None:
            source_error('请求地址含凭据，请移除后重新导入')
        path = parsed.path or '/'
        if not path.startswith('/') or path.startswith('//') or len(path) > 1024:
            source_error('请求路径无效或过长')
        if any((kind != 'OPENAPI' and _SENSITIVE.search(part) and part.casefold() not in
                {'token','tokens','oauth','authorization','csrf','xsrf','password','passwords','api-key'})
                or re.fullmatch(r'[A-Za-z0-9_-]{32,}', part) for part in path.split('/')):
            source_error('路径可能携带秘密，请替换为明确的资源参数后导入')
        if any(ord(char) < 32 for char in path) or '%' in path:
            source_error('请将编码路径转换为可审阅的参数模板后导入')
        query = [named(name, 'QUERY')
            for name, _value in parse_qsl(parsed.query, keep_blank_values=True)]
        all_parameters = {(item.location, item.name): item for item in (*parameters, *query)}
        safe_label = label if isinstance(label, str) and 0 < len(label) <= 256 and not _SENSITIVE.search(label) else method.upper() + ' ' + path
        key = method.upper() + '\0' + path
        requests.append(SourceRequest(item_id='req_' + hashlib.sha256(key.encode()).hexdigest()[:32],
            method=method.upper(), path=path, label=safe_label, pointer=pointer,
            parameters=tuple(all_parameters.values())))
        if len(requests) > 512:
            source_error('来源超过512个请求，请按业务范围拆分')

    if kind == 'OPENAPI':
        if not re.fullmatch(r'3\.[01]\.\d+', str(document.get('openapi', ''))):
            source_error('请选择 OpenAPI 3.0 或3.1 JSON文档')
        paths = document.get('paths')
        if not isinstance(paths, dict):
            source_error('OpenAPI缺少paths对象')
        for path, operations in paths.items():
            operations = resolved(operations)
            for method, operation in operations.items():
                if method.upper() not in _METHODS:
                    continue
                operation = resolved(operation)
                parameters = []
                shared,local=operations.get('parameters', []),operation.get('parameters', [])
                if not isinstance(shared,list) or not isinstance(local,list):
                    source_error('OpenAPI parameters必须是列表')
                for item in [*shared,*local]:
                    item = resolved(item)
                    location = {'path':'PATH', 'query':'QUERY', 'header':'HEADER'}.get(item.get('in'))
                    if location:
                        name = item.get('name', '')
                        parameters.append(named(name,location,item.get('required') is True))
                if 'requestBody' in operation:
                    content=resolved(operation['requestBody']).get('content',{})
                    if not isinstance(content,dict):
                        source_error('OpenAPI content必须是对象')
                    for media in content.values():
                        schema=resolved(resolved(media).get('schema',{}))
                        properties=schema.get('properties',{})
                        required=schema.get('required',[])
                        if not isinstance(properties,dict) or not isinstance(required,list):
                            source_error('OpenAPI正文属性结构无效')
                        parameters.extend(named(name,'BODY',name in required) for name in properties)
                add(method, path, operation.get('summary') or operation.get('operationId'),
                    '#/paths/' + path.replace('~', '~0').replace('/', '~1') + '/' + method, parameters)
    elif kind == 'HAR':
        log = document.get('log')
        if not isinstance(log, dict) or not isinstance(log.get('entries'), list):
            source_error('HAR缺少log.entries列表')
        for index, entry in enumerate(log['entries']):
            if not isinstance(entry, dict) or not isinstance(entry.get('request'), dict):
                source_error('HAR请求结构不完整')
            request = entry['request']
            add(request.get('method'), request.get('url'), None, f'#/log/entries/{index}/request', captured_fields(request))
    elif kind == 'POSTMAN':
        info=document.get('info')
        if not isinstance(info,dict) or info.get('schema') != 'https://schema.getpostman.com/json/collection/v2.1.0/collection.json':
            source_error('请选择Postman Collection v2.1 JSON')
        pending = [(document.get('item'), '#/item')]
        while pending:
            items, pointer = pending.pop()
            if not isinstance(items, list):
                source_error('Postman item必须是列表')
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    source_error('Postman集合项必须是对象')
                current = pointer + '/' + str(index)
                if 'item' in item:
                    pending.append((item['item'], current + '/item'))
                elif isinstance(item.get('request'), dict):
                    request = item['request']
                    url = request.get('url')
                    add(request.get('method'), url.get('raw') if isinstance(url, dict) else url,
                        item.get('name'), current + '/request', captured_fields(request))
                else:
                    source_error('Postman集合项缺少请求')
    else:
        source_error('不支持的来源类型')
    unique = {}
    for request in requests:
        unique.setdefault(request.item_id, request)
    return tuple(unique.values()), tuple(warnings)
