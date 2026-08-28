# PermissionContract 与治理来源的确定性构建器。
#
# 职责：从编译事实生成契约、关系和治理来源；保持 canonical/hash 输入输出等价。
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
    _CompilationFacts,
    _effect_id,
    _observation_requirement,
    _relation,
    _resource_type,
    _role_id,
    _sha256,
)
from product.backend.workflows.security_setup.local_observer_wiring import LocalObserverWiring
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



class ContractBuilderMixin:
    def _govern_contract(
        self,
        facts: _CompilationFacts,
        *,
        contract_id: str,
        actor: str,
        local_wiring: LocalObserverWiring | None = None,
    ) -> tuple[PermissionContract, bool]:
        with self._uow_factory() as work:
            project = work.projects.get(facts.project.project_id)
            active = work.contract_versions.get_active(
                facts.project.project_id,
                contract_id,
            )
            versions = work.contract_versions.list_for_contract(
                facts.project.project_id,
                contract_id,
            )
        if project is None:
            raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, "项目不存在")
        if project.governed_contract_id not in {None, contract_id}:
            raise JiejianError(
                ErrorCode.STATE_PRECONDITION,
                "当前项目正在使用高级权限契约；请先明确切换后再生成普通配置",
            )
        if active is not None:
            candidate = self._contract(facts, contract_id, active.version, local_wiring=local_wiring)
            if candidate == active.snapshot:
                return active.snapshot, True
            draft = self._contracts.revise_active(
                facts.project.project_id,
                contract_id,
                snapshot=self._contract(facts, contract_id, active.version + 1, local_wiring=local_wiring),
                sources=(self._source(facts),),
                actor=actor,
            )
        else:
            if versions:
                raise JiejianError(
                    ErrorCode.STATE_PRECONDITION,
                    "生成契约存在未完成版本，请先修复运行态后重试",
                )
            draft = self._contracts.create_draft(
                facts.project.project_id,
                contract_id,
                snapshot=self._contract(facts, contract_id, 1, local_wiring=local_wiring),
                sources=(self._source(facts),),
                actor=actor,
            )
        observations = (
            local_wiring.required_channels
            if local_wiring is not None
            else tuple(_observation_requirement(item.action_id) for item in facts.actions)
        )
        reviewed = self._contracts.submit_review(
            facts.project.project_id,
            contract_id,
            draft.version,
            actor=_ACTOR,
            available_observations=observations,
        )
        activated = self._contracts.activate_review(
            facts.project.project_id,
            contract_id,
            reviewed.version,
            actor=_ACTOR,
            available_observations=observations,
        )
        if activated.status is not ContractStatus.ACTIVE:
            raise JiejianError(ErrorCode.CONTRACT_NOT_ACTIVE, "生成契约未能激活")
        return activated.snapshot, False


    def _contract(
        self,
        facts: _CompilationFacts,
        contract_id: str,
        version: int,
        *,
        local_wiring: LocalObserverWiring | None = None,
    ) -> PermissionContract:
        identity_by_id = {item.identity_id: item for item in facts.identities}
        subject_ids = {
            identity_id
            for action in facts.actions
            for identity_id in (
                *(item.subject_test_identity_id for item in action.intents),
                action.setup.resource.owner_test_identity_id,
            )
        }
        try:
            subject_records = tuple(identity_by_id[item] for item in sorted(subject_ids))
        except KeyError as exc:
            raise JiejianError(
                ErrorCode.TEST_IDENTITY_NOT_READY,
                "权限意图引用的测试账号已经不存在",
            ) from exc
        subjects = tuple(
            SubjectDefinition(
                subject_id=item.identity_id,
                roles=(_role_id(item.role_candidate_id),),
                tenant_id="test-scope",
                department_id="test-scope",
            )
            for item in subject_records
        )
        resources: dict[str, ResourceDefinition] = {}
        relations: dict[str, RelationFact] = {}
        actions: list[ActionDefinition] = []
        effects: list[SecurityEffectDefinition] = []
        rules: list[PermissionRule] = []
        for action in facts.actions:
            setup = action.setup
            actual_resource_id = setup.resource.actual_resource_id
            if _CONTRACT_RESOURCE_ID.fullmatch(actual_resource_id) is None:
                raise JiejianError(
                    ErrorCode.STATE_PRECONDITION,
                    "测试资源标识不能安全进入确定性检查，请重新录制有限标识",
                    details={"action_id": action.action_id},
                )
            effect = setup.effect
            observation = setup.observation
            if effect is None or observation is None:
                raise JiejianError(
                    ErrorCode.STATE_PRECONDITION,
                    "业务动作缺少已确认安全效果或独立观察方式",
                    details={"action_id": action.action_id},
                )
            resource = ResourceDefinition(
                resource_id=actual_resource_id,
                resource_type=_resource_type(setup.resource.resource_type),
                tenant_id="test-scope",
                department_id="test-scope",
                owner_subject_id=setup.resource.owner_test_identity_id,
                workflow_state=_WORKFLOW_STATE,
            )
            existing_resource = resources.get(actual_resource_id)
            if existing_resource is not None and existing_resource != resource:
                raise JiejianError(
                    ErrorCode.STATE_PRECONDITION,
                    "多个业务动作对同一测试资源的确认事实不一致",
                )
            resources[actual_resource_id] = resource
            effect_id = _effect_id(action.action_id)
            effects.append(
                SecurityEffectDefinition(
                    effect_id=effect_id,
                    kind=effect.kind,
                    resource_type=resource.resource_type,
                    protected_fields=effect.protected_fields,
                )
            )
            actions.append(
                ActionDefinition(action_id=action.action_id, effect_ids=(effect_id,))
            )
            owns = _relation(
                RelationType.OWNS,
                setup.resource.owner_test_identity_id,
                "subject",
                actual_resource_id,
                "resource",
            )
            relations[owns.relation_id] = owns
            allow_intents = tuple(
                item
                for item in action.intents
                if item.expectation is PermissionExpectation.ALLOW
            )
            deny_intents = tuple(
                item
                for item in action.intents
                if item.expectation is PermissionExpectation.DENY
            )
            if not allow_intents or not deny_intents:
                raise JiejianError(
                    ErrorCode.STATE_PRECONDITION,
                    "业务动作必须同时确认一个允许主体和一个拒绝主体",
                    details={"action_id": action.action_id},
                )
            # 现有 Coverage 会把关系维度从 ALLOW 基线变异为 DENY Case。
            # DENY Intent 因此作为已确认候选主体参与计划，不能再生成一条
            # 自身也要求额外关系变异的重复规则，否则会制造伪 coverage gap。
            control = next(
                (
                    item
                    for item in allow_intents
                    if item.subject_test_identity_id
                    == setup.resource.owner_test_identity_id
                ),
                allow_intents[0],
            )
            relation_path = (owns.relation_id,)
            if control.subject_test_identity_id != setup.resource.owner_test_identity_id:
                scope = _relation(
                    RelationType.SAME_TENANT,
                    control.subject_test_identity_id,
                    "subject",
                    setup.resource.owner_test_identity_id,
                    "subject",
                )
                relations[scope.relation_id] = scope
                relation_path = (scope.relation_id, owns.relation_id)
            required_observations = (
                local_wiring.required_channels
                if local_wiring is not None
                else (_observation_requirement(action.action_id),)
            )
            rules.append(
                PermissionRule(
                    rule_id=f"rule-{control.fingerprint[:24]}",
                    subject_id=control.subject_test_identity_id,
                    action_id=action.action_id,
                    resource_id=actual_resource_id,
                    relation_path=relation_path,
                    context=PermissionContext(resource_ids=(actual_resource_id,)),
                    expectation=PermissionExpectation.ALLOW,
                    required_observations=required_observations,
                    coverage_dimensions=(CoverageDimension.RELATION,),
                    severity="critical",
                )
            )
        return PermissionContract(
            contract_id=contract_id,
            version=version,
            role_ids=tuple(
                sorted({role for subject in subjects for role in subject.roles})
            ),
            workflow_states=(_WORKFLOW_STATE,),
            subjects=subjects,
            effects=tuple(effects),
            actions=tuple(actions),
            resources=tuple(resources.values()),
            relations=tuple(relations.values()),
            rules=tuple(rules),
        )


    @staticmethod
    def _permission_target_classifier(
        classifier: HttpOutcomeClassifier,
        *,
        completion_binding: str | None = None,
    ) -> HttpOutcomeClassifier:
        """补齐权限拒绝结果，并让 202 只在既有异步完成事实闭合后被接受。"""

        accepted_statuses = {
            status
            for predicate in classifier.accepted
            if predicate.kind is HttpPredicateKind.STATUS_IN
            for status in predicate.statuses
        }
        denied_statuses = {
            status
            for predicate in classifier.denied
            if predicate.kind is HttpPredicateKind.STATUS_IN
            for status in predicate.statuses
        }
        additional = tuple(
            status
            for status in (401, 403, 404)
            if status not in accepted_statuses and status not in denied_statuses
        )
        updates: dict[str, object] = {}
        if additional:
            updates["denied"] = (
                *classifier.denied,
                HttpPredicate(
                    kind=HttpPredicateKind.STATUS_IN,
                    statuses=additional,
                ),
            )
        if (
            202 in accepted_statuses
            and classifier.completion_binding is None
            and completion_binding is not None
        ):
            updates["completion_binding"] = completion_binding
        if not updates:
            return classifier
        return classifier.model_copy(update=updates)

    @staticmethod
    def _source(facts: _CompilationFacts) -> SourceReference:
        return SourceReference(
            source_type=ContractSourceType.PROJECT_CONFIG,
            locator=f"permission-intent:{facts.project.project_id}",
            content_sha256=facts.authority_fingerprint,
        )
