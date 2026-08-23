# =============================================================================
# Recording / OpenAPI 到 HTTP 执行候选
#
# 定位
#   从已确认录制或受控 OpenAPI 中提取仍需人工确认的执行配置线索。
#
# 职责
#   投影请求与响应 Schema｜识别 producer-consumer 关系｜稳定排序候选优先级
#
# 边界
#   不生成 PermissionContract，不自动信任 security scheme，也不直接形成 HttpWorkflowBinding。
#
# 调用链
#   Recording / OpenAPI → HttpBindingCandidateBatch → GUI 人工确认 → Workflow compiler
# =============================================================================

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from product.backend.core.verification.permissions import permission_model_sha256
from product.protocols.http_binding_candidate import (
    HttpBindingCandidate,
    HttpBindingCandidateBatch,
    HttpBindingCandidateSource,
    HttpProducerConsumerKind,
    HttpProducerConsumerLink,
    HttpResponseSchemaCandidate,
)
from product.protocols.recording_flow import Flow


_HTTP_METHODS = {"GET", "PATCH", "POST", "PUT", "DELETE", "HEAD"}
_OPENAPI_MAX_BYTES = 1_048_576
_PATH_FIELD = re.compile(r"\{([A-Za-z][A-Za-z0-9_.-]{0,127})\}")


def build_recording_http_binding_candidates(flow: Flow) -> HttpBindingCandidateBatch:
    """Recording 只提供最高优先级的执行候选，仍保留人工确认门。"""

    if not isinstance(flow, Flow):
        raise TypeError("recording HTTP binding candidates require a confirmed Flow")
    candidates = tuple(
        _candidate(
            source=HttpBindingCandidateSource.RECORDING,
            source_locator=f"flow:{flow.id}/step:{step.id}",
            operation_id=step.id,
            method=step.request_template.method,
            path=step.request_template.path,
            path_fields=tuple(sorted(_PATH_FIELD.findall(step.request_template.path))),
            query_fields=tuple(sorted(item.name for item in step.request_template.query)),
            header_fields=tuple(sorted(item.name for item in step.request_template.headers)),
            request_schema_fingerprint=_recording_body_fingerprint(step.request_template.body),
            response_schemas=(
                HttpResponseSchemaCandidate(
                    status_code="recorded",
                    media_type="application/x-jiejian-extractors",
                    schema_fingerprint=permission_model_sha256(
                        tuple(
                            (
                                item.kind.value,
                                item.json_path,
                                item.header_name,
                                item.cookie_name,
                                item.selector,
                                item.attribute,
                            )
                            for item in step.request_template.response_extractors
                        )
                    ),
                    property_paths=tuple(
                        sorted(
                            {
                                value
                                for item in step.request_template.response_extractors
                                for value in (
                                    item.json_path,
                                    item.header_name,
                                    item.cookie_name,
                                )
                                if value is not None
                            }
                        )
                    ),
                ),
            ) if step.request_template.response_extractors else (),
            security_scheme_ids=(),
            links=tuple(
                HttpProducerConsumerLink(
                    kind=HttpProducerConsumerKind.SCHEMA_DEPENDENCY,
                    producer_operation_id=source.source_step_id,
                    consumer_operation_id=step.id,
                    consumer_field=source.name,
                    source_expression=source.json_path,
                )
                for source in step.variable_sources
            ),
        )
        for step in flow.steps
    )
    return HttpBindingCandidateBatch(
        candidates=tuple(sorted(candidates, key=lambda item: (item.source_priority, item.candidate_id))),
        input_fingerprint=permission_model_sha256(flow),
    )


def build_openapi_http_binding_candidates(
    document: Mapping[str, Any],
    *,
    source_locator: str = "openapi",
    max_bytes: int = _OPENAPI_MAX_BYTES,
) -> HttpBindingCandidateBatch:
    """解析有界 OpenAPI 执行线索；外部引用和不完整根结构严格拒绝。"""

    if not isinstance(document, Mapping) or not isinstance(document.get("paths"), Mapping):
        raise ValueError("OpenAPI HTTP binding source is invalid")
    encoded = json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8")
    if len(encoded) > max_bytes:
        raise ValueError("OpenAPI HTTP binding source exceeds its byte budget")
    if _contains_external_ref(document):
        raise ValueError("OpenAPI HTTP binding source cannot use external references")

    operations: list[dict[str, Any]] = []
    for path, path_item in sorted(document["paths"].items(), key=lambda item: str(item[0])):
        if not isinstance(path, str) or not path.startswith("/") or not isinstance(path_item, Mapping):
            continue
        path_parameters = path_item.get("parameters", ())
        for method, operation in sorted(path_item.items(), key=lambda item: str(item[0])):
            method_upper = str(method).upper()
            if method_upper not in _HTTP_METHODS or not isinstance(operation, Mapping):
                continue
            operation_id = str(operation.get("operationId") or f"{method_upper} {path}")
            parameters = tuple(
                item
                for item in (*_mapping_sequence(path_parameters), *_mapping_sequence(operation.get("parameters", ())))
                if isinstance(item.get("name"), str)
            )
            responses = _response_schemas(operation.get("responses", {}))
            response_fields = {
                field.rsplit(".", 1)[-1]
                for response in responses
                for field in response.property_paths
            }
            operations.append(
                {
                    "operation_id": operation_id,
                    "method": method_upper,
                    "path": path,
                    "path_fields": tuple(sorted({str(item["name"]) for item in parameters if item.get("in") == "path"} | set(_PATH_FIELD.findall(path)))),
                    "query_fields": tuple(sorted({str(item["name"]) for item in parameters if item.get("in") == "query"})),
                    "header_fields": tuple(sorted({str(item["name"]) for item in parameters if item.get("in") == "header"})),
                    "request_schema_fingerprint": _openapi_request_fingerprint(operation),
                    "response_schemas": responses,
                    "response_fields": response_fields,
                    "security_scheme_ids": _security_scheme_ids(document, operation),
                    "explicit_links": _explicit_links(operation_id, operation.get("responses", {})),
                }
            )

    candidates: list[HttpBindingCandidate] = []
    for operation in operations:
        consumer_fields = set(operation["path_fields"] + operation["query_fields"] + operation["header_fields"])
        links = list(operation["explicit_links"])
        for producer in operations:
            if producer is operation:
                continue
            for field in sorted(consumer_fields & producer["response_fields"]):
                links.append(
                    HttpProducerConsumerLink(
                        kind=HttpProducerConsumerKind.SCHEMA_DEPENDENCY,
                        producer_operation_id=producer["operation_id"],
                        consumer_operation_id=operation["operation_id"],
                        consumer_field=field,
                        source_expression=f"$response.body#/{field}",
                    )
                )
            for field in sorted(consumer_fields - producer["response_fields"]):
                matched = next(
                    (
                        candidate
                        for candidate in producer["response_fields"]
                        if _normalized_name(candidate) == _normalized_name(field)
                    ),
                    None,
                )
                if matched is not None:
                    links.append(
                        HttpProducerConsumerLink(
                            kind=HttpProducerConsumerKind.NAME_HEURISTIC,
                            producer_operation_id=producer["operation_id"],
                            consumer_operation_id=operation["operation_id"],
                            consumer_field=field,
                            source_expression=f"$response.body#/{matched}",
                        )
                    )
        links = list({permission_model_sha256(item): item for item in links}.values())
        source = (
            HttpBindingCandidateSource.OPENAPI_LINK
            if any(item.kind in {HttpProducerConsumerKind.OPENAPI_LINK, HttpProducerConsumerKind.LOCATION_HEADER} for item in links)
            else HttpBindingCandidateSource.SCHEMA_DEPENDENCY
            if any(item.kind is HttpProducerConsumerKind.SCHEMA_DEPENDENCY for item in links)
            else HttpBindingCandidateSource.NAME_HEURISTIC
        )
        candidates.append(
            _candidate(
                source=source,
                source_locator=f"{source_locator}:{operation['method']}:{operation['path']}",
                operation_id=operation["operation_id"],
                method=operation["method"],
                path=operation["path"],
                path_fields=operation["path_fields"],
                query_fields=operation["query_fields"],
                header_fields=operation["header_fields"],
                request_schema_fingerprint=operation["request_schema_fingerprint"],
                response_schemas=operation["response_schemas"],
                security_scheme_ids=operation["security_scheme_ids"],
                links=tuple(sorted(links, key=permission_model_sha256)),
            )
        )
    ordered = tuple(sorted(candidates, key=lambda item: (item.source_priority, item.candidate_id)))
    return HttpBindingCandidateBatch(
        candidates=ordered,
        input_fingerprint=permission_model_sha256(document),
    )


def _candidate(
    *,
    source: HttpBindingCandidateSource,
    source_locator: str,
    operation_id: str,
    method: str,
    path: str,
    path_fields: tuple[str, ...],
    query_fields: tuple[str, ...],
    header_fields: tuple[str, ...],
    request_schema_fingerprint: str | None,
    response_schemas: tuple[HttpResponseSchemaCandidate, ...],
    security_scheme_ids: tuple[str, ...],
    links: tuple[HttpProducerConsumerLink, ...],
) -> HttpBindingCandidate:
    priority = {
        HttpBindingCandidateSource.RECORDING: 0,
        HttpBindingCandidateSource.OPENAPI_LINK: 1,
        HttpBindingCandidateSource.SCHEMA_DEPENDENCY: 2,
        HttpBindingCandidateSource.NAME_HEURISTIC: 3,
    }[source]
    payload = {
        "source": source,
        "source_priority": priority,
        "source_locator": source_locator,
        "operation_id": operation_id,
        "method": method,
        "path": path,
        "path_fields": tuple(sorted(set(path_fields))),
        "query_fields": tuple(sorted(set(query_fields))),
        "header_fields": tuple(sorted(set(header_fields))),
        "request_schema_fingerprint": request_schema_fingerprint,
        "response_schemas": response_schemas,
        "security_scheme_ids": tuple(sorted(set(security_scheme_ids))),
        "producer_consumer_links": links,
        "requires_confirmation": True,
    }
    fingerprint = permission_model_sha256(payload)
    return HttpBindingCandidate(
        **payload,
        candidate_id=f"httpbind-{fingerprint[:32]}",
        candidate_fingerprint=fingerprint,
    )


def _response_schemas(value: Any) -> tuple[HttpResponseSchemaCandidate, ...]:
    if not isinstance(value, Mapping):
        return ()
    schemas: list[HttpResponseSchemaCandidate] = []
    for status, response in sorted(value.items(), key=lambda item: str(item[0])):
        if not isinstance(response, Mapping) or not isinstance(response.get("content"), Mapping):
            continue
        for media_type, media in sorted(response["content"].items(), key=lambda item: str(item[0])):
            if not isinstance(media, Mapping) or not isinstance(media.get("schema"), Mapping):
                continue
            shape = _openapi_schema_shape(media["schema"])
            schemas.append(
                HttpResponseSchemaCandidate(
                    status_code=str(status),
                    media_type=str(media_type),
                    schema_fingerprint=permission_model_sha256(shape),
                    property_paths=_property_paths(shape),
                )
            )
    return tuple(schemas)


def _explicit_links(producer_operation_id: str, responses: Any) -> tuple[HttpProducerConsumerLink, ...]:
    links: list[HttpProducerConsumerLink] = []
    if not isinstance(responses, Mapping):
        return ()
    for response in responses.values():
        if not isinstance(response, Mapping):
            continue
        response_links = response.get("links", {})
        if isinstance(response_links, Mapping):
            for link in response_links.values():
                if not isinstance(link, Mapping) or not isinstance(link.get("operationId"), str):
                    continue
                parameters = link.get("parameters", {})
                if isinstance(parameters, Mapping):
                    for field, expression in parameters.items():
                        if isinstance(field, str) and isinstance(expression, str):
                            links.append(HttpProducerConsumerLink(kind=HttpProducerConsumerKind.OPENAPI_LINK, producer_operation_id=producer_operation_id, consumer_operation_id=link["operationId"], consumer_field=field, source_expression=expression))
        headers = response.get("headers", {})
        if isinstance(headers, Mapping) and any(str(name).casefold() == "location" for name in headers):
            links.append(HttpProducerConsumerLink(kind=HttpProducerConsumerKind.LOCATION_HEADER, producer_operation_id=producer_operation_id, source_expression="$response.header.Location"))
    return tuple(links)


def _openapi_request_fingerprint(operation: Mapping[str, Any]) -> str | None:
    body = operation.get("requestBody")
    if not isinstance(body, Mapping) or not isinstance(body.get("content"), Mapping):
        return None
    shapes = tuple(
        (str(media_type), _openapi_schema_shape(media.get("schema", {})))
        for media_type, media in sorted(body["content"].items(), key=lambda item: str(item[0]))
        if isinstance(media, Mapping)
    )
    return permission_model_sha256(shapes) if shapes else None


def _recording_body_fingerprint(body: Any) -> str | None:
    kind = body.kind.value
    if kind == "EMPTY":
        return None
    if kind == "JSON":
        shape: Any = (kind, _value_shape(body.value))
    elif kind == "FORM_URLENCODED":
        shape = (kind, tuple(sorted(item.name for item in body.fields)))
    else:
        shape = (
            kind,
            tuple(
                sorted(
                    (
                        item.name,
                        item.content_type,
                        "fixture"
                        if item.fixture_artifact_id is not None
                        else "slot"
                        if item.slot_id is not None
                        else "literal",
                    )
                    for item in body.parts
                )
            ),
        )
    return permission_model_sha256(shape)


def _openapi_schema_shape(schema: Mapping[str, Any]) -> dict[str, Any]:
    shape: dict[str, Any] = {}
    for key in ("type", "format", "required", "readOnly", "writeOnly", "nullable"):
        value = schema.get(key)
        if isinstance(value, (str, bool)) or (key == "required" and isinstance(value, list)):
            shape[key] = tuple(sorted(str(item) for item in value)) if isinstance(value, list) else value
    properties = schema.get("properties")
    if isinstance(properties, Mapping):
        shape["properties"] = {
            str(name): _openapi_schema_shape(value)
            for name, value in sorted(properties.items(), key=lambda item: str(item[0]))
            if isinstance(value, Mapping)
        }
    items = schema.get("items")
    if isinstance(items, Mapping):
        shape["items"] = _openapi_schema_shape(items)
    reference = schema.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/"):
        shape["$ref"] = reference
    return shape


def _property_paths(shape: Mapping[str, Any], prefix: str = "") -> tuple[str, ...]:
    properties = shape.get("properties")
    if not isinstance(properties, Mapping):
        return ()
    paths: list[str] = []
    for name, child in properties.items():
        path = f"{prefix}.{name}" if prefix else str(name)
        paths.append(path)
        if isinstance(child, Mapping):
            paths.extend(_property_paths(child, path))
    return tuple(sorted(paths))


def _value_shape(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _value_shape(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return ("array", tuple(_value_shape(item) for item in value[:1]))
    if value is None:
        return "null"
    return type(value).__name__


def _security_scheme_ids(document: Mapping[str, Any], operation: Mapping[str, Any]) -> tuple[str, ...]:
    security = operation.get("security", document.get("security", ()))
    return tuple(
        sorted(
            {
                str(name)
                for requirement in _mapping_sequence(security)
                for name in requirement
            }
        )
    )


def _mapping_sequence(value: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _contains_external_ref(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            (key == "$ref" and (not isinstance(item, str) or not item.startswith("#/")))
            or _contains_external_ref(item)
            for key, item in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_external_ref(item) for item in value)
    return False


def _normalized_name(value: str) -> str:
    return re.sub(r"(?:^|[_-])(resource|object|project|document)", "", value.casefold()).replace("_", "").replace("-", "")
