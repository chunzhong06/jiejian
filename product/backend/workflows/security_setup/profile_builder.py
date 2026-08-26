# WebExecutionProfile、workflow、observer 与发布工件的确定性构建器。
#
# 职责：从编译事实生成执行 Profile 与发布工件；保持 workflow、observer 和 hash 语义等价。
# 边界：不执行目标、不读取秘密正文、不调用 LLM，不改变 Verification 语义。

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
from product.backend.workflows.security_setup.models import (
    _ActionFacts,
    _CompilationFacts,
    _effect_id,
    _observation_requirement,
    _observer_id,
    _profile_id,
    _replace_resource_slot,
)
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



class ProfileBuilderMixin:
    def _profile(
        self,
        facts: _CompilationFacts,
        contract: PermissionContract,
    ) -> WebExecutionProfile:
        identity_by_id = {item.identity_id: item for item in facts.identities}
        required_identity_ids = {
            identity_id
            for action in facts.actions
            for identity_id in (
                *(item.subject_test_identity_id for item in action.intents),
                action.setup.resource.owner_test_identity_id,
            )
        }
        identities = tuple(
            self._execution_credentials.profile_identity(identity_by_id[item])
            for item in sorted(required_identity_ids)
        )
        workflows = tuple(self._workflow(action) for action in facts.actions)
        observers = tuple(self._observer(action) for action in facts.actions)
        profile_id = _profile_id(facts.authority_fingerprint)
        return WebExecutionProfile(
            profile_id=profile_id,
            project_id=facts.project.project_id,
            project_name=facts.project.name,
            target=self._target(facts.understanding.confirmed_endpoint),
            identities=identities,
            contract_id=contract.contract_id,
            contract_version=contract.version,
            observers=observers,
            subject_bindings=tuple(
                SubjectExecutionBinding(
                    subject_id=item.identity_id,
                    identity_id=item.identity_id,
                )
                for item in identities
            ),
            workflow_bindings=workflows,
            effect_bindings=tuple(
                EffectBinding(
                    effect_id=_effect_id(action.action_id),
                    required_channels=(
                        _observation_requirement(action.action_id),
                    ),
                    closure_policy=EffectClosurePolicy.IMMEDIATE,
                    projection_version="v1",
                )
                for action in facts.actions
            ),
            observer_bindings=tuple(
                ObserverRequirementBinding(
                    requirement_id=_observation_requirement(action.action_id),
                    kind=ObserverRequirementKind.OBSERVER_SPEC,
                        observer_id=_observer_id(action.action_id),
                    observer_type=ObserverType.OWNER_API,
                    identity_id=action.setup.resource.owner_test_identity_id,
                    phases=(
                        ObservationPhase.BASELINE,
                        ObservationPhase.BEFORE,
                        ObservationPhase.AFTER,
                    ),
                )
                for action in facts.actions
            ),
            seed=int(facts.authority_fingerprint[:15], 16),
            case_budget=min(8192, max(8, sum(len(item.intents) for item in facts.actions) * 4)),
            max_relation_depth=8,
            max_duration_us=300_000_000,
        )


    def _workflow(self, action: _ActionFacts) -> HttpWorkflowBinding:
        setup = action.setup
        recovery = setup.recovery
        if recovery is None or recovery.kind is not RecoveryBindingKind.RECORDED_REQUEST:
            raise JiejianError(
                ErrorCode.STATE_PRECONDITION,
                "当前动作没有可执行的已录制恢复请求",
                details={"action_id": action.action_id},
            )
        steps = [
            HttpWorkflowStep(
                id=step.id,
                purpose=step.purpose,
                identity_id=CASE_SUBJECT_IDENTITY,
                request_template=step.request_template,
                classifier=(
                    self._permission_target_classifier(step.classifier)
                    if step.purpose is WorkflowStepPurpose.TARGET
                    else step.classifier
                ),
                depends_on_step_ids=step.depends_on_step_ids,
            )
            for step in action.flow.steps
        ]
        cleanup_id = f"cleanup-{hashlib.sha256(action.action_id.encode()).hexdigest()[:24]}"
        cleanup_template = self._cleanup_template(recovery, cleanup_id)
        steps.append(
            HttpWorkflowStep(
                id=cleanup_id,
                purpose=WorkflowStepPurpose.CLEANUP,
                identity_id=recovery.test_identity_id,
                request_template=cleanup_template,
                classifier=HttpOutcomeClassifier(
                    accepted=(
                        HttpPredicate(
                            kind=HttpPredicateKind.STATUS_IN,
                            statuses=(200, 201, 204),
                        ),
                    ),
                    denied=(
                        HttpPredicate(
                            kind=HttpPredicateKind.STATUS_IN,
                            statuses=(401, 403, 404),
                        ),
                    ),
                ),
                depends_on_step_ids=(action.flow.target_step_id,),
                failure_policy=WorkflowFailurePolicy.STOP,
            )
        )
        workflow_id = f"workflow-{hashlib.sha256(action.action_id.encode()).hexdigest()[:24]}"
        return HttpWorkflowBinding(
            workflow_id=workflow_id,
            source_flow_id=action.flow.id,
            action_id=action.action_id,
            steps=tuple(steps),
            target_step_id=action.flow.target_step_id,
            baseline_projections=(
                BaselineProjection(
                    projection_id=f"projection-{hashlib.sha256(action.action_id.encode()).hexdigest()[:20]}",
                    logical_resource_handle="case-resource",
                    normalization_version="1",
                    projection_version="1",
                    integrity_mode=BaselineIntegrityMode.EXACT_RESTORE,
                ),
            ),
            reset_strategy=UniqueResourceWorkflowResetStrategy(
                workflow_id=workflow_id,
            ),
        )


    @staticmethod
    def _cleanup_template(recovery: Any, cleanup_id: str) -> HttpRequestTemplate:
        path = str(recovery.path_template)
        slots: list[ValueSlot] = []
        if "{case_resource_id}" in path:
            path = path.replace("{case_resource_id}", "{recovery_resource_path}")
            slots.append(
                ValueSlot(
                    slot_id="recovery_resource_path",
                    source=ValueSlotSource.CASE_RESOURCE_ID,
                    consumer=ValueSlotConsumer.PATH,
                    consumer_step_id=cleanup_id,
                )
            )
        body_value, body_uses_resource = _replace_resource_slot(
            recovery.json_body_template
        )
        if body_uses_resource:
            slots.append(
                ValueSlot(
                    slot_id="recovery_resource_body",
                    source=ValueSlotSource.CASE_RESOURCE_ID,
                    consumer=ValueSlotConsumer.JSON_BODY,
                    consumer_step_id=cleanup_id,
                )
            )
        return HttpRequestTemplate(
            method=recovery.method,
            path=path,
            body=(JsonBody(value=body_value) if body_value else EmptyBody()),
            input_slots=tuple(slots),
        )


    def _observer(self, action: _ActionFacts) -> ObserverSpec:
        observation = action.setup.observation
        if observation is None:
            raise JiejianError(
                ErrorCode.STATE_PRECONDITION,
                "当前动作缺少可信所有者观察方式",
            )
        token = hashlib.sha256(action.action_id.encode()).hexdigest()[:20]
        return ObserverSpec(
            observer_id=_observer_id(action.action_id),
            observer_type=ObserverType.OWNER_API,
            target=ObserverTarget(
                target_id=f"observer-target-{token}",
                locator=OwnerApiLocator(
                    relative_path_template=observation.path_template.replace(
                        "{case_resource_id}",
                        "{resource_id}",
                    )
                ),
                normalization_id=f"normalizer-{token}",
                normalization_version="1",
            ),
            phases=(
                ObservationPhase.BASELINE,
                ObservationPhase.BEFORE,
                ObservationPhase.AFTER,
            ),
            required=True,
            budget=ObserverBudget(
                timeout_us=5_000_000,
                max_rows=1,
                max_bytes=262_144,
            ),
        )


    @staticmethod
    def _target(endpoint: str | None) -> WebTargetDefinition:
        if endpoint is None:
            raise JiejianError(ErrorCode.APPLICATION_ENDPOINT_INVALID, "本地应用地址尚未确认")
        parsed = urlsplit(endpoint)
        if parsed.hostname is None:
            raise JiejianError(ErrorCode.APPLICATION_ENDPOINT_INVALID, "本地应用地址无效")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return WebTargetDefinition(
            scope=WebTargetScope(
                base_url=endpoint,
                allowed_origins=(endpoint,),
                allowed_hosts=(parsed.hostname,),
                allowed_ports=(port,),
                allow_private_network=True,
                timeout_seconds=5,
                max_requests=128,
                max_response_bytes=262_144,
            ),
            reset_path="/__jiejian_unused_reset",
        )


    def _write_profile(self, project_id: str, digest: str, raw: bytes) -> Path:
        directory = self._generated_dir(project_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{digest}.json"
        if path.exists():
            if path.read_bytes() != raw:
                raise JiejianError(
                    ErrorCode.ARTIFACT_HASH_MISMATCH,
                    "生成配置内容寻址校验失败",
                )
            return path
        temporary = directory / f".{digest}.{os.getpid()}.tmp"
        try:
            temporary.write_bytes(raw)
            os.replace(temporary, path)
        except OSError:
            temporary.unlink(missing_ok=True)
            raise JiejianError(
                ErrorCode.EXECUTION_PROFILE_STORAGE_FAILED,
                "无法保存内部检查配置",
            ) from None
        return path


    def _generated_dir(self, project_id: str) -> Path:
        return (
            self._var_dir
            / "data"
            / "projects"
            / project_id
            / "execution"
            / "generated"
        ).resolve()
