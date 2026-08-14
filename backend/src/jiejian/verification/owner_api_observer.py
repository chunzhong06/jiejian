# =============================================================================
# V1 owner_api → Observer V2 兼容适配
#
# 定位
#   复用现有 HttpExecutor 的请求、TargetGuard、预算、超时、重定向和脱敏边界，
#   将可信 owner_api 响应短暂转换为 Observer V2，再显式投影回 V1 Observation。
#
# 安全边界
#   不执行第二次请求，不重试、不降级、不决定 Verdict；V1 执行器继续消费 V1
#   Observation，V2 envelope 只作为本批公共协议边界。
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..protocols.observer_v2 import (
    CausalityStatus,
    CorrelationV2,
    ObservationCompleteness,
    ObservationEnvelopeV2,
    ObservationPhase,
    ObservationProvenanceV2,
    ObservationWindowV2,
    ObserverBudgetV2,
    ObserverSpecV2,
    ObserverTargetV2,
    ObserverType,
    OwnerApiLocatorV2,
    ProvenanceType,
    build_normalized_state,
    canonical_sha256,
)
from .models import Observation
from ..redaction import redact_known_secrets


@dataclass(frozen=True, slots=True)
class OwnerApiObserverV2Adapter:
    """把一个既有 owner_api GET 转换为 V2 envelope 并提供 V1 投影。"""

    spec: ObserverSpecV2
    utc_now_us: Callable[[], int]

    @classmethod
    def for_path(
        cls,
        path_template: str,
        *,
        timeout_us: int,
        max_bytes: int,
        utc_now_us: Callable[[], int],
    ) -> OwnerApiObserverV2Adapter:
        spec = ObserverSpecV2(
            observer_id="owner_api",
            observer_type=ObserverType.OWNER_API,
            target=ObserverTargetV2(
                target_id="owner-api-state",
                locator=OwnerApiLocatorV2(relative_path_template=path_template),
                normalization_id="owner-api-state",
                normalization_version="1.0",
            ),
            phases=(
                ObservationPhase.INITIAL,
                ObservationPhase.BASELINE,
                ObservationPhase.BEFORE,
                ObservationPhase.AFTER,
            ),
            required=True,
            budget=ObserverBudgetV2(timeout_us=timeout_us, max_rows=1, max_bytes=max_bytes),
        )
        return cls(spec=spec, utc_now_us=utc_now_us)

    def observe(
        self,
        executor: object,
        *,
        resource_id: str,
        owner_token: str,
        case_id: str,
        phase: ObservationPhase,
        known_secrets: tuple[str, ...] = (),
    ) -> ObservationEnvelopeV2:
        """执行与 V1 相同的一次 GET；异常仍交给现有 V1 错误映射。"""

        locator = self.spec.target.locator
        assert isinstance(locator, OwnerApiLocatorV2)
        started_at_us = self.utc_now_us()
        response = executor.request(
            "GET",
            locator.relative_path_template.format(resource_id=resource_id),
            case_id=case_id,
            bearer_token=owner_token,
        )
        finished_at_us = self.utc_now_us()
        safe_data = redact_known_secrets(response.data, known_secrets)
        payload = {"status_code": response.status_code, "data": safe_data}
        window = ObservationWindowV2(
            phase=phase,
            started_at_us=started_at_us,
            finished_at_us=finished_at_us,
            timeout_us=self.spec.budget.timeout_us,
        )
        correlation = CorrelationV2(
            case_id=case_id,
            resource_id=resource_id,
            request_marker=case_id,
        )
        if 200 <= response.status_code < 300:
            state = build_normalized_state(payload, known_secrets=known_secrets)
            return ObservationEnvelopeV2(
                observer_id=self.spec.observer_id,
                observer_type=self.spec.observer_type,
                phase=phase,
                target_id=self.spec.target.target_id,
                window=window,
                correlation=correlation,
                causality=CausalityStatus.CORRELATED,
                completeness=ObservationCompleteness.COMPLETE,
                state=state,
                provenance=ObservationProvenanceV2(
                    provenance_type=ProvenanceType.OWNER_API,
                    adapter_version="owner-api-v2-compat-1",
                    target_id=self.spec.target.target_id,
                    source_sha256=canonical_sha256(payload),
                ),
            )
        return ObservationEnvelopeV2(
            observer_id=self.spec.observer_id,
            observer_type=self.spec.observer_type,
            phase=phase,
            target_id=self.spec.target.target_id,
            window=window,
            correlation=correlation,
            causality=CausalityStatus.CORRELATED,
            completeness=ObservationCompleteness.MISSING,
            reason_codes=("OWNER_API_UNAVAILABLE",),
        )


def project_owner_envelope_to_v1(envelope: ObservationEnvelopeV2) -> Observation:
    """唯一的 owner_api V2→V1 投影，保持旧字段与小写阶段语义。"""

    if envelope.observer_type is not ObserverType.OWNER_API or envelope.completeness is not ObservationCompleteness.COMPLETE:
        raise ValueError("only a complete OWNER_API envelope can project to V1")
    if envelope.state is None:
        raise ValueError("complete OWNER_API envelope requires state")
    payload = envelope.state.canonical_data
    status_code = payload.get("status_code")
    data = payload.get("data")
    if not isinstance(status_code, int) or not isinstance(data, dict):
        raise ValueError("owner_api envelope state is not a V1 response")
    return Observation(
        observer="owner_api",
        phase=envelope.phase.value.lower(),
        status_code=status_code,
        data=data,
    )
