# Security setup 编译事实与 builder 共享的内部模型。

# =============================================================================
# 普通权限意图确定性编译器
#
# 定位
#   PermissionIntent 与受治理 PermissionContract、内部 WebExecutionProfile 之间的唯一桥接。
#
# 职责
#   汇总当前权威输入｜生成稳定 Contract/Profile｜登记内部执行配置｜拒绝旧生成配置。
#
# 边界
#   不执行目标、不读取秘密正文、不调用 LLM，也不改变 Verification 或安全结论语义。
#
# 调用链
#   Permission API / Readiness → SecuritySetupCompiler → Governance / ExecutionWorkflow
# =============================================================================

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.contracts.models import ContractSourceType, SourceReference
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import ContractStatus, ProjectStatus
from product.backend.core.permission_intent import PermissionIntent
from product.backend.core.test_identity import TestIdentity
from product.backend.core.test_setup import (
    ActionSafetySetup,
    RecoveryBindingKind,
)
from product.backend.core.verification.permissions import (
    ActionDefinition,
    CoverageDimension,
    PermissionContext,
    PermissionContract,
    PermissionExpectation,
    PermissionRule,
    RelationEndpoint,
    RelationFact,
    RelationType,
    ResourceDefinition,
    SecurityEffectDefinition,
    SubjectDefinition,
)
from product.backend.infra.storage import ExecutionProfileRecord, StorageUnitOfWork
from product.backend.workflows.contracts.governance import ContractGovernance
from product.backend.workflows.permission_intents import (
    PermissionIntentMatrixView,
    PermissionIntentService,
)
from product.backend.workflows.recording.lifecycle import RecordingLifecycle
from product.backend.workflows.runs.execution import ExecutionWorkflow
from product.backend.workflows.test_identities import TestIdentityExecutionCredentials
from product.protocols import (
    BaselineIntegrityMode,
    BaselineProjection,
    EffectBinding,
    EffectClosurePolicy,
    EmptyBody,
    HttpOutcomeClassifier,
    HttpPredicate,
    HttpPredicateKind,
    HttpRequestTemplate,
    HttpWorkflowBinding,
    HttpWorkflowStep,
    JsonBody,
    ObservationPhase,
    ObserverBudget,
    ObserverRequirementBinding,
    ObserverRequirementKind,
    ObserverSpec,
    ObserverTarget,
    ObserverType,
    OwnerApiLocator,
    SubjectExecutionBinding,
    ValueSlot,
    ValueSlotConsumer,
    ValueSlotSource,
    WebExecutionProfile,
    WebTargetDefinition,
    WebTargetScope,
    WorkflowFailurePolicy,
    WorkflowStepPurpose,
    canonical_web_execution_profile_json_bytes,
)
from product.protocols.recording_flow import Flow
from product.protocols.web.workflow import (
    CASE_SUBJECT_IDENTITY,
    UniqueResourceWorkflowResetStrategy,
)


_CONTRACT_RESOURCE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_ACTOR = "界鉴确定性编译器"
_WORKFLOW_STATE = "READY"


class _CompileModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class SecuritySetupCompileResult(_CompileModel):
    project_id: str
    authority_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    contract_id: str
    contract_version: int = Field(ge=1)
    contract_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_id: str
    profile_path: str
    profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    covered_action_ids: tuple[str, ...]
    reused: bool


@dataclass(frozen=True, slots=True)
class _ResolvedIntent:
    """编译瞬间为组级要求选择的临时账号代表。"""

    intent: PermissionIntent
    subject_test_identity_id: str

    @property
    def expectation(self) -> PermissionExpectation:
        return self.intent.expectation

    @property
    def fingerprint(self) -> str:
        return self.intent.fingerprint


@dataclass(frozen=True, slots=True)
class _ActionFacts:
    action_id: str
    setup: ActionSafetySetup
    flow: Flow
    intents: tuple[_ResolvedIntent, ...]


@dataclass(frozen=True, slots=True)
class _CompilationFacts:
    project: Any
    understanding: Any
    identities: tuple[TestIdentity, ...]
    matrix: PermissionIntentMatrixView
    actions: tuple[_ActionFacts, ...]
    authority_fingerprint: str


def _replace_resource_slot(value: Any) -> tuple[Any, bool]:
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        used = False
        for key, child in value.items():
            replaced, child_used = _replace_resource_slot(child)
            output[key] = replaced
            used = used or child_used
        return output, used
    if isinstance(value, list):
        output_list: list[Any] = []
        used = False
        for child in value:
            replaced, child_used = _replace_resource_slot(child)
            output_list.append(replaced)
            used = used or child_used
        return output_list, used
    if value == "{case_resource_id}":
        return {"$slot": "recovery_resource_body"}, True
    return value, False


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _json_value(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(child) for child in value]
    return value


def _sha256(value: Any) -> str:
    encoded = json.dumps(
        _json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _contract_id(project_id: str) -> str:
    return f"generated-contract-{hashlib.sha256(project_id.encode()).hexdigest()[:24]}"


def _profile_id(authority: str) -> str:
    return f"generated-{authority[:32]}"


def _role_id(candidate_id: str) -> str:
    return f"role-{candidate_id.removeprefix('role_')[:24]}"


def _resource_type(value: str) -> str:
    return f"resource-{hashlib.sha256(value.encode()).hexdigest()[:16]}"


def _effect_id(action_id: str) -> str:
    return f"effect-{hashlib.sha256(action_id.encode()).hexdigest()[:24]}"


def _observation_requirement(action_id: str) -> str:
    return f"resource_state_{hashlib.sha256(action_id.encode()).hexdigest()[:20]}"


def _observer_id(action_id: str) -> str:
    return f"observer-{hashlib.sha256(action_id.encode()).hexdigest()[:20]}"


def _relation(
    relation_type: RelationType,
    source_id: str,
    source_type: str,
    target_id: str,
    target_type: str,
) -> RelationFact:
    digest = _sha256((relation_type.value, source_type, source_id, target_type, target_id))
    return RelationFact(
        relation_id=f"relation-{digest[:24]}",
        relation=relation_type,
        source=RelationEndpoint(endpoint_type=source_type, endpoint_id=source_id),
        target=RelationEndpoint(endpoint_type=target_type, endpoint_id=target_id),
    )
