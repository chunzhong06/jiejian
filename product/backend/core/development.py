# 轻量开发任务、冻结开工上下文和交付回执；不保存第二套权限或安全结论。
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from product.protocols.execution_v3 import Hash, LogicalId, PermissionReference, WireModel
from product.protocols.runtime_identity import ControlledRuntimeReference

TaskId = Annotated[str, Field(pattern=r"^dvt_[0-9a-f]{32}$")]
ContextId = Annotated[str, Field(pattern=r"^ctx_[0-9a-f]{32}$")]
DeliveryId = Annotated[str, Field(pattern=r"^dly_[0-9a-f]{32}$")]
OperationId = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
OperationKind = Literal["CREATE", "REVISE", "ACCEPT", "DELIVER", "CLOSE", "CANCEL"]


class DevelopmentTask(WireModel):
    schema_version: Literal["1"] = "1"
    task_id: TaskId
    project_id: LogicalId
    status: Literal["ACTIVE", "CLOSED", "CANCELLED"] = "ACTIVE"
    version: int = Field(ge=1)
    revision: int = Field(ge=1)
    context_id: ContextId
    created_at_us: int = Field(ge=0)
    updated_at_us: int = Field(ge=0)


class DevelopmentContext(WireModel):
    schema_version: Literal["1"] = "1"
    context_id: ContextId
    task_id: TaskId
    project_id: LogicalId
    revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=120)
    goal: str = Field(min_length=1, max_length=4000)
    start_snapshot_id: Annotated[str, Field(pattern=r"^snp_[0-9a-f]{32}$")]
    source_fingerprint: Hash
    policy_epoch: int = Field(ge=0)
    permission_refs: tuple[PermissionReference, ...] = Field(min_length=1, max_length=4096)
    created_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def ordered_permissions(self):
        keys = tuple(item.intent_id for item in self.permission_refs)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("context permissions must be ordered and unique")
        return self


class DevelopmentAcceptance(WireModel):
    schema_version: Literal["1"] = "1"
    context_id: ContextId
    task_id: TaskId
    project_id: LogicalId
    client_name: str = Field(min_length=1, max_length=128)
    accepted_at_us: int = Field(ge=0)


class DevelopmentDelivery(WireModel):
    schema_version: Literal["1"] = "1"
    delivery_id: DeliveryId
    context_id: ContextId
    task_id: TaskId
    project_id: LogicalId
    ordinal: int = Field(ge=1)
    change_id: Annotated[str, Field(pattern=r"^chg_[0-9a-f]{32}$")]
    previous_delivery_id: DeliveryId | None = None
    start_snapshot_id: Annotated[str, Field(pattern=r"^snp_[0-9a-f]{32}$")]
    current_snapshot_id: Annotated[str, Field(pattern=r"^snp_[0-9a-f]{32}$")]
    created_at_us: int = Field(ge=0)


class DevelopmentReceipt(WireModel):
    schema_version: Literal["1"] = "1"
    project_id: LogicalId
    operation_id: OperationId
    kind: OperationKind
    request_fingerprint: Hash
    status: Literal["SUCCEEDED"] = "SUCCEEDED"
    task_id: TaskId
    task_version: int = Field(ge=1)
    context_id: ContextId
    delivery_id: DeliveryId | None = None
    change_id: Annotated[str, Field(pattern=r"^chg_[0-9a-f]{32}$")] | None = None
    created_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def delivery_result(self):
        if (self.kind == "DELIVER") != (self.delivery_id is not None and self.change_id is not None):
            raise ValueError("delivery receipt requires exact delivery and change")
        if self.kind != "DELIVER" and (self.delivery_id is not None or self.change_id is not None):
            raise ValueError("non-delivery receipt cannot contain delivery references")
        return self


class RuntimeActivationReceipt(WireModel):
    schema_version: Literal["1"] = "1"
    kind: Literal["LOAD_RUNTIME"] = "LOAD_RUNTIME"
    project_id: LogicalId
    operation_id: OperationId
    request_fingerprint: Hash
    task_id: TaskId
    delivery_id: DeliveryId
    source_fingerprint: Hash
    status: Literal["PENDING", "SUCCEEDED", "FAILED", "UNKNOWN"]
    runtime_reference: ControlledRuntimeReference | None = None
    error_code: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,127}$")
    created_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_receipt(self):
        if self.status == "SUCCEEDED" and (self.runtime_reference is None or self.runtime_reference.source_fingerprint != self.source_fingerprint):
            raise ValueError("runtime success requires corresponding source and instance")
        return self
