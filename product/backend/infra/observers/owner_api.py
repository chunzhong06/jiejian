# =============================================================================
# owner_api → Observer 适配
#
# 定位
#   复用现有 HttpExecutionAdapter 的请求、TargetGuard、预算、超时、重定向和脱敏边界，
#   将可信 owner_api 响应转换为当前 Observer 。
#
# 安全边界
#   不执行第二次请求，不重试、不降级、不决定 Verdict。
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from product.protocols.observer import CausalityStatus, Correlation, ObservationCompleteness, ObservationEnvelope, ObservationPhase, ObservationProvenance, ObservationWindow, ObserverBudget, ObserverSpec, ObserverTarget, ObserverType, OwnerApiLocator, ProvenanceType, build_normalized_state, canonical_sha256
from product.backend.core.redaction import redact_known_secrets


@dataclass(frozen=True, slots=True)
class OwnerApiObserverAdapter:
    """把一个既有 owner_api GET 转换为当前 Observation envelope。"""

    spec: ObserverSpec
    utc_now_us: Callable[[], int]

    @classmethod
    def for_path(
        cls,
        path_template: str,
        *,
        timeout_us: int,
        max_bytes: int,
        utc_now_us: Callable[[], int],
    ) -> OwnerApiObserverAdapter:
        spec = ObserverSpec(
            observer_id="owner_api",
            observer_type=ObserverType.OWNER_API,
            target=ObserverTarget(
                target_id="owner-api-state",
                locator=OwnerApiLocator(relative_path_template=path_template),
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
            budget=ObserverBudget(timeout_us=timeout_us, max_rows=1, max_bytes=max_bytes),
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
    ) -> ObservationEnvelope:
        """执行一次有界 GET；异常仍交给 Runner 的统一错误映射。"""

        locator = self.spec.target.locator
        assert isinstance(locator, OwnerApiLocator)
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
        window = ObservationWindow(
            phase=phase,
            started_at_us=started_at_us,
            finished_at_us=finished_at_us,
            timeout_us=self.spec.budget.timeout_us,
        )
        correlation = Correlation(
            case_id=case_id,
            resource_id=resource_id,
            request_marker=case_id,
        )
        if 200 <= response.status_code < 300:
            state = build_normalized_state(payload, known_secrets=known_secrets)
            return ObservationEnvelope(
                observer_id=self.spec.observer_id,
                observer_type=self.spec.observer_type,
                phase=phase,
                target_id=self.spec.target.target_id,
                window=window,
                correlation=correlation,
                causality=CausalityStatus.CORRELATED,
                completeness=ObservationCompleteness.COMPLETE,
                state=state,
                provenance=ObservationProvenance(
                    provenance_type=ProvenanceType.OWNER_API,
                    adapter_version="owner-api-1",
                    target_id=self.spec.target.target_id,
                    source_sha256=canonical_sha256(payload),
                ),
            )
        return ObservationEnvelope(
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
