# 受控检查配置注册端口；只接受显式来源和精确效果能力，不扫描 provider 或推断身份映射。
from __future__ import annotations

from threading import RLock

from pydantic import Field, model_validator

from product.backend.core.action_preparation import RegisteredObserverReference
from product.backend.core.business_boundary import BusinessEffectDefinition
from product.backend.core.check_plan import RegisteredEffectProofCapability
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols.check_runtime import CheckBudget, CheckIdentityVerification, CheckAuxiliarySource, SafeLabel
from product.protocols.execution_v3 import Hash, IdentityId, LogicalId, WireModel, content_hash
from product.protocols.observer import ObserverSpec
from product.protocols.web.target import WebTargetScope


class RegisteredCheckIdentity(WireModel):
    identity_id: IdentityId
    verification: CheckIdentityVerification


class RegisteredResourceWindow(WireModel):
    binding_fingerprint: Hash
    exclusive_resource_window: bool


class RegisteredAuxiliarySource(WireModel):
    source: CheckAuxiliarySource
    spec: ObserverSpec

    @model_validator(mode="after")
    def validate_spec(self):
        if self.source.observer_id != self.spec.observer_id:
            raise ValueError("auxiliary observer mismatch")
        if self.source.trace_namespace is not None and self.spec.observer_type.value != "STRUCTURED_AUDIT_LOG":
            raise ValueError("trace requires explicit structured audit source")
        return self


class RegisteredCheckProof(WireModel):
    reference: RegisteredObserverReference
    effect: BusinessEffectDefinition
    spec: ObserverSpec
    observation_identity_id: IdentityId
    source_label: SafeLabel
    source_location: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_./:-]{0,255}$")
    closure_supported: bool
    resource_correlation_supported: bool
    exclusive_resource_window: bool = False
    auxiliary_sources: tuple[RegisteredAuxiliarySource, ...] = Field(default=(), max_length=5)

    @model_validator(mode="after")
    def validate_observer(self):
        if self.reference.observer_id != self.spec.observer_id:
            raise ValueError("registered observer identity mismatch")
        if ".." in self.source_location.split("/") or ":" in self.source_location.split("/")[0]:
            raise ValueError("registered source location escaped")
        return self


class CheckRuntimeRegistration(WireModel):
    project_id: LogicalId
    source_fingerprint: Hash
    target: WebTargetScope | None = None
    budget: CheckBudget | None = None
    identities: tuple[RegisteredCheckIdentity, ...] = Field(default=(), max_length=4096)
    proofs: tuple[RegisteredCheckProof, ...] = Field(default=(), max_length=256)
    resource_windows: tuple[RegisteredResourceWindow, ...] = Field(default=(), max_length=4096)

    @model_validator(mode="after")
    def validate_unique(self):
        keys = [(item.reference.descriptor_id, item.reference.descriptor_fingerprint,
            item.reference.observer_id, item.effect.effect_id) for item in self.proofs]
        if len(set(keys)) != len(keys) or len({item.identity_id for item in self.identities}) != len(self.identities):
            raise ValueError("duplicate controlled check registration")
        if len({item.binding_fingerprint for item in self.resource_windows}) != len(self.resource_windows):
            raise ValueError("duplicate resource window registration")
        specs = {}
        for item in self.proofs:
            for spec in (item.spec, *(source.spec for source in item.auxiliary_sources)):
                if spec.observer_id in specs and specs[spec.observer_id] != spec:
                    raise ValueError("conflicting observer configuration")
                specs[spec.observer_id] = spec
        return self

    @property
    def fingerprint(self):
        return content_hash("CheckRuntimeRegistration", self.model_dump(mode="json"))


class CheckRuntimeRegistry:
    """主线程/受控编译器显式注册的进程内快照；API 与模型没有 writer 入口。"""

    def __init__(self):
        self._lock = RLock()
        self._snapshots = {}

    def register(self, snapshot: CheckRuntimeRegistration, *, expected_fingerprint: str | None = None):
        snapshot = CheckRuntimeRegistration.model_validate_json(snapshot.model_dump_json(), strict=True)
        with self._lock:
            previous = self._snapshots.get(snapshot.project_id)
            if previous == snapshot:
                return snapshot.fingerprint
            if (None if previous is None else previous.fingerprint) != expected_fingerprint:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "准备来源已变化")
            self._snapshots[snapshot.project_id] = snapshot
        return snapshot.fingerprint

    def snapshot(self, project_id: str) -> CheckRuntimeRegistration | None:
        with self._lock:
            return self._snapshots.get(project_id)

    def unregister(self, project_id: str) -> None:
        with self._lock:
            self._snapshots.pop(project_id,None)

    def proof(self, project_id: str, reference: RegisteredObserverReference, effect_id: str):
        snapshot = self.snapshot(project_id)
        return None if snapshot is None else next((item for item in snapshot.proofs
            if item.reference == reference and item.effect.effect_id == effect_id), None)

    def contains(self, project_id, reference):
        snapshot = self.snapshot(project_id)
        return snapshot is not None and any(item.reference == reference for item in snapshot.proofs)

    def capability(self, project_id, reference, effect_id):
        proof = self.proof(project_id, reference, effect_id)
        return None if proof is None else RegisteredEffectProofCapability(**reference.model_dump(), effect_id=effect_id,
            closure_supported=proof.closure_supported, resource_correlation_supported=proof.resource_correlation_supported)
