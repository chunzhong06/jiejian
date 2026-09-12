# 冻结 v3 动作的 Web 执行适配；复用目标防护与身份隔离，不接收旧 Contract/Profile。
from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
import re
import os
from typing import Callable

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.execution.web.adapter import HttpExecutionAdapter, HttpResponse, extract_response_value
from product.backend.infra.execution.web.identity import HttpIdentityRuntime
from product.protocols.check_runtime import CheckActionConfig, CheckRuntimeBundle
from product.protocols.execution_v3 import ExecutionCase
from product.protocols.web.request import HttpRequestTemplate, ValueSlotSource
from product.protocols.web.response import ResponseExtractor, ResponseExtractorKind, _read_json_path


class CheckWebRuntime:
    def __init__(self, bundle: CheckRuntimeBundle, *, environ: Mapping[str, str],
                 cancellation_requested: Callable[[], bool], reserved_origins: tuple[str, ...] = (), request_scope=None):
        self.bundle = bundle
        self._environ = environ
        self._request_scope = request_scope
        self._identities = {item.identity_id: item for item in bundle.identities}
        self._executed: set[str] = set()
        self._actual_identities: dict[str, str] = {}
        self.adapter = HttpExecutionAdapter(bundle.target,
            cleanup_reserve=bundle.budget.recovery_reserve_requests,
            known_secrets=tuple(environ[name] for name in check_secret_names(bundle) if environ.get(name)),
            cancellation_requested=cancellation_requested, reserved_origins=reserved_origins,
            request_marker=self.request_marker, executor_process_id=os.getpid())

    def request_marker(self, case_id: str) -> str:
        if self._request_scope is None:
            return case_id
        from product.protocols.check_result import check_request_marker
        return check_request_marker(*self._request_scope, case_id)

    def close(self):
        self.adapter.close()
        self._target_responses = {}

    def target_response(self, case_id):
        return getattr(self, "_target_responses", {}).get(case_id)

    def target_attempted(self, case_id: str) -> bool:
        return case_id in self._executed

    def actual_identity_status(self, case_id: str) -> str:
        return self._actual_identities.get(case_id, "UNKNOWN")

    @contextmanager
    def identity_session(self, identity_id: str):
        definition = self._identities.get(identity_id)
        if definition is None:
            raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_READY, "执行身份与所需凭据类型不一致，请重新生成检查配置")
        runtime = HttpIdentityRuntime(definition.binding, resolve_secret=self._secret,
            business_origin=self.bundle.target.base_url)
        try:
            runtime.bootstrap(lambda *_args, **_kwargs: None)
            yield runtime
        finally:
            runtime.close()

    def _secret(self, reference: str) -> str | None:
        return self._environ.get(reference.removeprefix("env:"))

    def verify_identity(self, identity_id: str, case: ExecutionCase, *, cleanup=False) -> str:
        with self.identity_session(identity_id) as runtime:
            return self._verify_identity(runtime, identity_id, case, cleanup=cleanup)

    def _verify_identity(self, runtime: HttpIdentityRuntime, identity_id: str, case: ExecutionCase, *, cleanup=False) -> str:
        definition = self._identities[identity_id]
        verification = definition.verification
        if verification is None:
            return "UNKNOWN"
        try:
            _, response = self.adapter.execute_detailed(verification.request, case_id=case.case_id,
                action_id="identity-verification", identity_runtime=runtime, cleanup_request=cleanup)
            if not 200 <= response.status_code < 300:
                return "UNKNOWN"
            found, subject = _read_json_path(response.data, verification.subject_json_path)
            if not found or not isinstance(subject, str):
                return "UNKNOWN"
            return "MATCH" if subject == verification.expected_application_subject_id else "MISMATCH"
        except JiejianError:
            return "UNKNOWN"

    def request(self, template: HttpRequestTemplate, *, case: ExecutionCase, action_id: str,
                identity_id: str, cleanup=False) -> HttpResponse:
        with self.identity_session(identity_id) as runtime:
            _, response = self.adapter.execute_detailed(template, case_id=case.case_id, action_id=action_id,
                slot_values=self._values(template, case, {}), identity_runtime=runtime, cleanup_request=cleanup)
            return response

    def execute_flow(self, action: CheckActionConfig, case: ExecutionCase, *, verify_identity=False):
        """每个 Case 的 TARGET 最多发送一次；传输异常后也不清除已执行标记。"""
        if case.case_id in self._executed:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "TARGET already executed for this case session")
        responses: dict[str, HttpResponse] = {}
        with self.identity_session(case.subject_test_identity_id) as runtime:
            for step in action.steps:
                if step.purpose == "TARGET":
                    # SETUP 可能改变会话；实际主体确认必须紧邻 TARGET 且复用同一身份容器。
                    identity_status = self._verify_identity(runtime, case.subject_test_identity_id, case) if verify_identity else None
                    self._actual_identities[case.case_id] = identity_status or "UNKNOWN"
                    self._executed.add(case.case_id)
                execution, response = self.adapter.execute_detailed(step.request, case_id=case.case_id,
                    action_id=action.action_id, classifier=step.classifier,
                    slot_values=self._values(step.request, case, responses), identity_runtime=runtime)
                responses[step.step_id] = response
                if step.purpose == "TARGET":
                    if not hasattr(self, "_target_responses"):
                        self._target_responses = {}
                    self._target_responses[case.case_id] = response
                    return (execution, response, identity_status) if verify_identity else (execution, response)
                if execution.outcome.value != "ACCEPTED":
                    raise JiejianError(ErrorCode.SETUP_STEP_FAILED, "工作流步骤依赖无法满足")
        raise JiejianError(ErrorCode.RUNNER_PROTOCOL_INVALID, "执行快照格式无效")

    def _values(self, template: HttpRequestTemplate, case: ExecutionCase,
                responses: Mapping[str, HttpResponse]) -> dict[str, object]:
        values: dict[str, object] = {}
        for slot in template.input_slots:
            if slot.source is ValueSlotSource.CASE_RESOURCE_ID:
                value = case.resource_id
            elif slot.source is ValueSlotSource.CASE_SUBJECT_ID:
                value = case.subject_test_identity_id
            elif slot.source is ValueSlotSource.FIXED_LITERAL:
                value = slot.literal
            elif slot.source is ValueSlotSource.SECRET_REF:
                value = self._secret(slot.secret_ref or "")
            else:
                response = responses.get(slot.producer_step_id or "")
                if response is None:
                    raise JiejianError(ErrorCode.VALUE_EXTRACTION_FAILED, "动态值生产步骤尚未完成")
                kinds = {ValueSlotSource.PRIOR_STEP_JSON_PATH: ResponseExtractorKind.JSON_PATH,
                    ValueSlotSource.PRIOR_STEP_HEADER: ResponseExtractorKind.HEADER,
                    ValueSlotSource.PRIOR_STEP_COOKIE: ResponseExtractorKind.COOKIE,
                    ValueSlotSource.PRIOR_STEP_LOCATION: ResponseExtractorKind.LOCATION}
                kind = kinds[slot.source]
                selector = {"JSON_PATH": "json_path", "HEADER": "header_name", "COOKIE": "cookie_name"}.get(kind.value)
                extractor = ResponseExtractor(extractor_id=slot.slot_id, kind=kind, max_length=slot.max_length,
                    secret=slot.secret, **({selector: slot.source_path} if selector else {}))
                value = extract_response_value(response, extractor)
            if value is None or (isinstance(value, str) and len(value) > slot.max_length):
                raise JiejianError(ErrorCode.VALUE_EXTRACTION_FAILED, "动态值超过长度预算")
            values[slot.slot_id] = value
        return values


def check_secret_names(bundle: CheckRuntimeBundle) -> tuple[str, ...]:
    """从严格冻结结构中收集引用名称；不查询秘密或继承无关环境变量。"""
    names: set[str] = set()
    def visit(value, key=None):
        if isinstance(value, dict):
            for name, child in value.items():
                visit(child, name)
        elif isinstance(value, list):
            for child in value:
                visit(child, key)
        elif isinstance(value, str) and key is not None and key.endswith("_ref") and re.fullmatch(r"env:[A-Z_][A-Z0-9_]{0,127}", value):
            names.add(value[4:])
    visit(bundle.model_dump(mode="json"))
    return tuple(sorted(names))
