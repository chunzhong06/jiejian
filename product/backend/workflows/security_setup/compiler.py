# Security setup 编译总编排；不重复 Contract/Profile builder 规则。

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
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.contracts.models import ContractSourceType, SourceReference
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import ContractStatus, ProjectStatus
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
    _ResolvedIntent,
    SecuritySetupCompileResult,
    _contract_id,
    _profile_id,
    _sha256,
)
from product.backend.workflows.security_setup.local_observer_wiring import (
    LocalObserverWiring,
    load_local_observer_wiring,
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



from .contract_builder import ContractBuilderMixin
from .profile_builder import ProfileBuilderMixin

class SecuritySetupCompiler(ContractBuilderMixin, ProfileBuilderMixin):
    def __init__(
        self,
        uow_factory: Callable[..., StorageUnitOfWork],
        *,
        var_dir: Path,
        permission_intents: PermissionIntentService,
        execution_credentials: TestIdentityExecutionCredentials,
        contracts: ContractGovernance,
        execution: ExecutionWorkflow,
        local_observer_environment_resolver: Callable[
            [str, str | None], str | None
        ]
        | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._var_dir = var_dir.resolve()
        self._permission_intents = permission_intents
        self._execution_credentials = execution_credentials
        self._contracts = contracts
        self._execution = execution
        self._local_observer_environment_resolver = (
            local_observer_environment_resolver or (lambda _source, _origin: None)
        )


    def compile(self, project_id: str) -> SecuritySetupCompileResult:
        """生成或复用当前权限意图对应的治理契约和内容寻址 Profile。"""

        self._permission_intents.refresh_bindings(project_id)
        facts = self._collect(project_id, require_compilable=True)
        facts, local_wiring = self._with_local_observer_wiring(facts)
        contract_id = _contract_id(project_id)
        contract, reused = self._govern_contract(
            facts,
            contract_id=contract_id,
            actor=_ACTOR,
            local_wiring=local_wiring,
        )
        profile = self._profile(facts, contract, local_wiring=local_wiring)
        raw = canonical_web_execution_profile_json_bytes(profile)
        profile_sha256 = hashlib.sha256(raw).hexdigest()
        profile_path = self._write_profile(project_id, profile_sha256, raw)
        record = self._execution.register_generated(profile_path)
        self._mark_project_ready(project_id)
        return SecuritySetupCompileResult(
            project_id=project_id,
            authority_fingerprint=facts.authority_fingerprint,
            contract_id=contract.contract_id,
            contract_version=contract.version,
            contract_fingerprint=record.contract_fingerprint,
            profile_id=record.profile_id,
            profile_path=record.source_path,
            profile_sha256=profile_sha256,
            covered_action_ids=tuple(item.action_id for item in facts.actions),
            reused=reused,
        )


    def validate_generated_profile(
        self,
        record: ExecutionProfileRecord,
        profile: WebExecutionProfile,
    ) -> None:
        """只约束 generated 目录中的内部配置；历史外部配置不属于普通检查真源。"""

        generated = self._generated_dir(record.project_id)
        try:
            Path(record.source_path).resolve().relative_to(generated)
        except ValueError:
            raise JiejianError(
                ErrorCode.EXECUTION_PROFILE_SOURCE_DRIFT,
                "检查配置不是由当前项目安全准备生成",
            ) from None
        try:
            authority_facts = self._collect(
                record.project_id,
                require_compilable=False,
            )
            authority_facts, _ = self._with_local_observer_wiring(authority_facts)
            authority = authority_facts.authority_fingerprint
        except JiejianError as exc:
            raise JiejianError(
                ErrorCode.EXECUTION_PROFILE_SOURCE_DRIFT,
                "普通权限设置已经失效，请重新确认并生成检查配置",
            ) from exc
        if profile.profile_id != _profile_id(authority):
            raise JiejianError(
                ErrorCode.EXECUTION_PROFILE_SOURCE_DRIFT,
                "普通权限设置已经变化，请重新生成检查配置",
            )


    def is_current(self, project_id: str) -> bool:
        """返回普通模式生成契约与 Profile 是否仍绑定当前权威输入。"""

        return self.current_generated_profile_id(project_id) is not None


    def current_generated_profile_id(self, project_id: str) -> str | None:
        """返回唯一当前 Generated Profile；历史外部配置不能冒充普通模式就绪。"""

        try:
            facts = self._collect(project_id, require_compilable=False)
            facts, _ = self._with_local_observer_wiring(facts)
            with self._uow_factory() as work:
                project = work.projects.get(project_id)
            if (
                project is None
                or project.governed_contract_id != _contract_id(project_id)
            ):
                return None
            profile_id = _profile_id(facts.authority_fingerprint)
            self._execution.current(profile_id, project_id=project_id)
            return profile_id
        except JiejianError:
            return None


    def _with_local_observer_wiring(
        self,
        facts: _CompilationFacts,
    ) -> tuple[_CompilationFacts, LocalObserverWiring | None]:
        """把受控本地描述纳入普通 Profile 指纹，避免外部配置静默陈旧。"""

        descriptor_path = self._local_observer_environment_resolver(
            facts.understanding.source_root,
            facts.understanding.confirmed_endpoint,
        )
        if descriptor_path is None:
            return facts, None
        matches: list[LocalObserverWiring] = []
        for action in facts.actions:
            wiring = load_local_observer_wiring(
                descriptor_path,
                var_dir=self._var_dir,
                action_id=action.action_id,
                expected_origin=facts.understanding.confirmed_endpoint,
                expected_resource_id=action.setup.resource.actual_resource_id,
                resource_mismatch_is_disabled=len(facts.actions) > 1,
            )
            if wiring is not None:
                matches.append(wiring)
        if len(matches) != 1:
            raise JiejianError(
                ErrorCode.STATE_PRECONDITION,
                "本地观察环境必须唯一绑定一个已确认业务动作",
            )
        wiring = matches[0]
        return replace(
            facts,
            authority_fingerprint=_sha256(
                (facts.authority_fingerprint, wiring.descriptor_fingerprint)
            ),
        ), wiring


    def _collect(
        self,
        project_id: str,
        *,
        require_compilable: bool,
    ) -> _CompilationFacts:
        matrix = self._permission_intents.matrix(project_id)
        current_executions = self._permission_intents.execution_intents(project_id)
        active_revisions = self._permission_intents.current_intents(project_id)
        policy_snapshot = self._permission_intents.policy_snapshot(project_id)
        with self._uow_factory() as work:
            project = work.projects.get(project_id)
            understanding = work.application_understanding.get(project_id)
            identities = work.test_identities.list_for_project(project_id)
            setups = {
                action.action_candidate_id: work.action_safety_setups.get_for_action(
                    project_id,
                    action.action_candidate_id,
                )
                for action in matrix.actions
            }
            recordings = {
                setup.resource.recording_id: work.recordings.get(
                    setup.resource.recording_id
                )
                for setup in setups.values()
                if setup is not None
            }
        if project is None or understanding is None:
            raise JiejianError(
                ErrorCode.STATE_PRECONDITION,
                "项目尚未形成可编译的应用理解事实",
            )
        flows: dict[str, Flow | None] = {}
        for action_id, setup in setups.items():
            recording = (
                None if setup is None else recordings.get(setup.resource.recording_id)
            )
            try:
                flows[action_id] = (
                    None
                    if recording is None
                    else RecordingLifecycle.load_final_flow(
                        RecordingLifecycle.flow_path(self._var_dir, recording)
                    )
                )
            except JiejianError:
                flows[action_id] = None
        authority = _sha256(
            {
                # governed_contract_* 与 updated_at_us 是本编译器的输出，不能反向污染输入指纹。
                "project": {
                    "project_id": project.project_id,
                    "name": project.name,
                    "target_type": project.target_type,
                },
                "understanding": understanding,
                "identities": identities,
                "permission_policy": policy_snapshot,
                "action_setups": tuple(
                    (action_id, setups[action_id], flows.get(action_id))
                    for action_id in sorted(setups)
                ),
            }
        )
        compilable = {item.action_candidate_id for item in matrix.actions if item.compilable}
        actions: list[_ActionFacts] = []
        for action_id in sorted(compilable):
            setup = setups.get(action_id)
            flow = flows.get(action_id)
            intents = tuple(
                sorted(
                    (
                        _ResolvedIntent(
                            revision=item.revision,
                            binding=item.binding,
                            subject_test_identity_id=item.subject_test_identity_id,
                        )
                        for item in current_executions
                        if item.binding.action_candidate_id == action_id
                        and item.gap is None
                        and item.subject_test_identity_id is not None
                    ),
                    key=lambda item: item.subject_test_identity_id,
                )
            )
            if setup is None or flow is None or not intents:
                if require_compilable:
                    raise JiejianError(
                        ErrorCode.STATE_PRECONDITION,
                        "已确认动作缺少当前流程或安全恢复事实",
                        details={"action_id": action_id},
                    )
                continue
            actions.append(
                _ActionFacts(
                    action_id=action_id,
                    setup=setup,
                    flow=flow,
                    intents=intents,
                )
            )
        if require_compilable and len(current_executions) != len(active_revisions):
            raise JiejianError(
                ErrorCode.STATE_PRECONDITION,
                "存在需要重新映射的权限要求，不能生成检查配置",
            )
        if require_compilable and not actions:
            raise JiejianError(
                ErrorCode.STATE_PRECONDITION,
                "请先为至少一个业务动作确认允许和拒绝权限组，并准备可用测试账号",
            )
        return _CompilationFacts(
            project=project,
            understanding=understanding,
            identities=tuple(sorted(identities, key=lambda item: item.identity_id)),
            matrix=matrix,
            actions=tuple(actions),
            authority_fingerprint=authority,
        )


    def _mark_project_ready(self, project_id: str) -> None:
        """仅在生成配置完整登记后开放现有提交链，避免任意 DRAFT 被执行。"""

        with self._uow_factory() as work:
            project = work.projects.get(project_id)
            if project is None:
                raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, "项目不存在")
            if project.status is ProjectStatus.ARCHIVED:
                raise JiejianError(
                    ErrorCode.STATE_PRECONDITION,
                    "归档项目不能生成普通检查配置",
                )
            if project.status is ProjectStatus.READY:
                return
            work.projects.replace(
                project.model_copy(
                    update={
                        "status": ProjectStatus.READY,
                        "updated_at_us": max(
                            project.updated_at_us + 1,
                            time.time_ns() // 1_000,
                        ),
                    }
                )
            )
            work.commit()
