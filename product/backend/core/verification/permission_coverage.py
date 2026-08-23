# =============================================================================
# 权限关系覆盖规划
#
# 定位
#   将显式权限意图编译为有限、可解释、确定性的关系覆盖计划。
#
# 职责
#   生成普通与批量变异 case｜记录覆盖路径｜显式报告预算和关系缺口
#
# 边界
#   只消费 Contract 内的声明事实和调用方提供的有界 ID 集合；不执行请求、
#   不查询目标、不推断缺失关系，也不生成全笛卡尔积。
#
# 调用链
#   ExecutionWorkflow → build_permission_coverage_plan → PermissionCoveragePlan
# =============================================================================

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import Field, model_validator

from product.backend.core.verification.permissions import BatchAuthorizationMode, BatchPermissionRule, BatchResourceExpectation, CoverageDimension, PermissionContract, PermissionContext, PermissionExpectation, PermissionModel, PermissionRule, RelationFact, RelationType, permission_model_sha256


class CoverageGapCode(StrEnum):
    MISSING_SUBJECT = "MISSING_SUBJECT"
    MISSING_RESOURCE = "MISSING_RESOURCE"
    MISSING_OBSERVER = "MISSING_OBSERVER"
    RELATION_UNPROVABLE = "RELATION_UNPROVABLE"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    RELATION_DEPTH_EXCEEDED = "RELATION_DEPTH_EXCEEDED"


class EliminatedReason(StrEnum):
    DUPLICATE_SEMANTICS = "DUPLICATE_SEMANTICS"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"


class CoverageStatus(StrEnum):
    COVERED = "COVERED"
    GAP = "GAP"


class RetentionReason(StrEnum):
    EXPLICIT_ALLOW_BASELINE = "EXPLICIT_ALLOW_BASELINE"
    EXPLICIT_DENY_RISK = "EXPLICIT_DENY_RISK"
    RECENT_NEIGHBOR = "RECENT_NEIGHBOR"
    BATCH_AUTHORIZATION = "BATCH_AUTHORIZATION"


class PermissionMutationCase(PermissionModel):
    case_id: str = Field(pattern=r"^case-[0-9a-f]{32}$")
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    finding_pre_identity: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_rule_ids: tuple[str, ...] = Field(min_length=1, max_length=32)
    dimensions: tuple[CoverageDimension, ...] = Field(max_length=6)
    retention_reason: RetentionReason
    subject_id: str
    action_id: str
    resource_ids: tuple[str, ...] = Field(min_length=1, max_length=256)
    expectations: tuple[PermissionExpectation, ...] = Field(min_length=1, max_length=256)
    relation_paths: tuple[tuple[str, ...], ...] = Field(min_length=1, max_length=256)
    context: PermissionContext
    required_observations: tuple[str, ...] = Field(min_length=1, max_length=16)
    batch_mode: BatchAuthorizationMode | None = None
    atomic: bool = False

    @model_validator(mode="after")
    def validate_shape(self) -> PermissionMutationCase:
        if len(self.resource_ids) != len(self.expectations) or len(self.resource_ids) != len(self.relation_paths):
            raise ValueError("resource_ids, expectations, and relation_paths must align")
        if len(set(self.source_rule_ids)) != len(self.source_rule_ids):
            raise ValueError("source_rule_ids must be unique")
        if len(set(self.dimensions)) != len(self.dimensions):
            raise ValueError("dimensions must be unique")
        is_batch = len(self.resource_ids) > 1
        if is_batch and self.batch_mode is None:
            raise ValueError("batch cases require batch_mode")
        if not is_batch and self.batch_mode is not None:
            raise ValueError("ordinary cases must not declare batch_mode")
        if self.atomic and not is_batch:
            raise ValueError("atomic is only valid for batch cases")
        return self


class CoverageRecord(PermissionModel):
    rule_id: str
    dimension: CoverageDimension | None = None
    expectation: PermissionExpectation | None = None
    status: CoverageStatus
    case_ids: tuple[str, ...] = Field(default=(), max_length=32)
    gap_codes: tuple[CoverageGapCode, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def validate_target(self) -> CoverageRecord:
        if (self.dimension is None) == (self.expectation is None):
            raise ValueError("coverage record requires exactly one dimension or expectation")
        return self


class CoverageGap(PermissionModel):
    rule_id: str
    dimension: CoverageDimension | None = None
    expectation: PermissionExpectation | None = None
    code: CoverageGapCode
    detail: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_target(self) -> CoverageGap:
        if (self.dimension is None) == (self.expectation is None):
            raise ValueError("coverage gap requires exactly one dimension or expectation")
        return self


class EliminatedCandidate(PermissionModel):
    candidate_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_rule_ids: tuple[str, ...] = Field(min_length=1, max_length=32)
    reason: EliminatedReason


class PermissionMutationPlan(PermissionModel):
    plan_id: str = Field(pattern=r"^plan-[0-9a-f]{32}$")
    plan_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    contract_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    seed: int
    engine_version: str = Field(min_length=1, max_length=128)
    case_budget: int = Field(ge=0, le=8192)
    candidate_count: int = Field(ge=0, le=8192)
    retained_count: int = Field(ge=0, le=8192)
    cases: tuple[PermissionMutationCase, ...] = Field(max_length=8192)
    coverage: tuple[CoverageRecord, ...] = Field(max_length=16384)
    gaps: tuple[CoverageGap, ...] = Field(max_length=16384)
    eliminated: tuple[EliminatedCandidate, ...] = Field(max_length=16384)

    @model_validator(mode="after")
    def validate_counts(self) -> PermissionMutationPlan:
        if self.candidate_count < self.retained_count:
            raise ValueError("retained_count cannot exceed candidate_count")
        if self.retained_count != len(self.cases):
            raise ValueError("retained_count must equal the case count")
        return self


@dataclass(frozen=True)
class _Candidate:
    semantic: dict[str, Any]
    source_rule_ids: tuple[str, ...]
    dimensions: tuple[CoverageDimension, ...]
    retention_reason: RetentionReason
    priority: int
    case: PermissionMutationCase
    target_keys: tuple[tuple[str, CoverageDimension | None, PermissionExpectation | None], ...]


def _path_index(contract: PermissionContract) -> dict[tuple[str, str], tuple[RelationFact, ...]]:
    index: dict[tuple[str, str], list[RelationFact]] = {}
    for relation in contract.relations:
        index.setdefault((relation.source.endpoint_type, relation.source.endpoint_id), []).append(relation)
    return {key: tuple(sorted(value, key=lambda item: item.relation_id)) for key, value in index.items()}


def _find_path(
    contract: PermissionContract,
    subject_id: str,
    resource_id: str,
    *,
    max_relation_depth: int,
) -> tuple[str, ...] | None:
    if max_relation_depth < 1:
        return None
    index = _path_index(contract)
    queue: deque[tuple[tuple[str, str], tuple[str, ...]]] = deque(
        [(('subject', subject_id), ())]
    )
    visited = {("subject", subject_id)}
    while queue:
        endpoint, path = queue.popleft()
        if endpoint == ("resource", resource_id):
            return path
        if len(path) >= max_relation_depth:
            continue
        for relation in index.get(endpoint, ()):
            next_endpoint = (relation.target.endpoint_type, relation.target.endpoint_id)
            if next_endpoint in visited:
                continue
            visited.add(next_endpoint)
            queue.append((next_endpoint, path + (relation.relation_id,)))
    return None


def _same_scope(left: Any, right: Any) -> bool:
    return (
        left.tenant_id is not None
        and left.tenant_id == right.tenant_id
        and left.department_id is not None
        and left.department_id == right.department_id
    )


def _subject_order(current: Any, candidate: Any) -> tuple[Any, ...]:
    return (
        abs(candidate.admin_level - current.admin_level),
        tuple(candidate.roles),
        candidate.subject_id,
    )


def _candidate_case(
    *,
    contract: PermissionContract,
    source_rule_ids: tuple[str, ...],
    dimensions: tuple[CoverageDimension, ...],
    retention_reason: RetentionReason,
    priority: int,
    subject_id: str,
    action_id: str,
    resource_ids: tuple[str, ...],
    expectations: tuple[PermissionExpectation, ...],
    relation_paths: tuple[tuple[str, ...], ...],
    context: PermissionContext,
    required_observations: tuple[str, ...],
    batch_mode: BatchAuthorizationMode | None = None,
    atomic: bool = False,
    engine_version: str,
    include_baseline_target: bool = True,
) -> _Candidate:
    semantic = {
        "engine_version": engine_version,
        "subject_id": subject_id,
        "action_id": action_id,
        "resource_ids": resource_ids,
        "expectations": expectations,
        "relation_paths": relation_paths,
        "context": context,
        "required_observations": required_observations,
        "batch_mode": batch_mode,
        "atomic": atomic,
    }
    fingerprint = permission_model_sha256(semantic)
    subjects = {item.subject_id: item for item in contract.subjects}
    resources = {item.resource_id: item for item in contract.resources}
    relation_index = {item.relation_id: item.relation for item in contract.relations}
    subject = subjects[subject_id]
    resource_classes = tuple(
        {
            "resource_type": resources[resource_id].resource_type,
            "workflow_state": resources[resource_id].workflow_state,
            "is_child": resources[resource_id].parent_resource_id is not None,
        }
        for resource_id in resource_ids
    )
    finding_pre_identity = permission_model_sha256(
        {
            "subject_class": {
                "roles": subject.roles,
                "admin_level": subject.admin_level,
                "scope": tuple(
                    {
                        "same_tenant": subject.tenant_id == resources[resource_id].tenant_id,
                        "same_department": subject.department_id == resources[resource_id].department_id,
                    }
                    for resource_id in resource_ids
                ),
            },
            "action_id": action_id,
            "resource_classes": resource_classes,
            "expectations": expectations,
            "relation_types": tuple(tuple(relation_index[relation_id].value for relation_id in path) for path in relation_paths),
            "context": {
                "workflow_states": context.workflow_states,
                "has_tenant_scope": bool(context.tenant_ids),
                "has_department_scope": bool(context.department_ids),
            },
            "batch_mode": batch_mode,
            "atomic": atomic,
        }
    )
    case = PermissionMutationCase(
        case_id=f"case-{fingerprint[:32]}",
        fingerprint=fingerprint,
        finding_pre_identity=finding_pre_identity,
        source_rule_ids=source_rule_ids,
        dimensions=dimensions,
        retention_reason=retention_reason,
        subject_id=subject_id,
        action_id=action_id,
        resource_ids=resource_ids,
        expectations=expectations,
        relation_paths=relation_paths,
        context=context,
        required_observations=required_observations,
        batch_mode=batch_mode,
        atomic=atomic,
    )
    return _Candidate(
        semantic=semantic,
        source_rule_ids=source_rule_ids,
        dimensions=dimensions,
        retention_reason=retention_reason,
        priority=priority,
        case=case,
        target_keys=tuple(
            ([(source_rule_ids[0], None, expectations[0])] if include_baseline_target else [])
            + [(source_rule_ids[0], dimension, None) for dimension in dimensions]
        ),
    )


def _gap(
    gaps: list[CoverageGap], rule_id: str, dimension: CoverageDimension | None, expectation: PermissionExpectation | None, code: CoverageGapCode, detail: str
) -> None:
    gaps.append(CoverageGap(rule_id=rule_id, dimension=dimension, expectation=expectation, code=code, detail=detail))


def _missing_observations(required: tuple[str, ...], available: set[str]) -> bool:
    return not set(required).issubset(available)


def _nearest_subject(
    contract: PermissionContract,
    current_id: str,
    dimension: CoverageDimension,
) -> str | None:
    current = next(subject for subject in contract.subjects if subject.subject_id == current_id)
    candidates = [subject for subject in contract.subjects if subject.subject_id != current_id]
    if dimension is CoverageDimension.ROLE:
        candidates = [subject for subject in candidates if _same_scope(current, subject) and (subject.roles != current.roles or subject.admin_level != current.admin_level)]
    elif dimension is CoverageDimension.TENANT:
        candidates = [subject for subject in candidates if subject.tenant_id != current.tenant_id]
        candidates.sort(key=lambda subject: (subject.roles != current.roles, abs(subject.admin_level - current.admin_level), subject.subject_id))
        return candidates[0].subject_id if candidates else None
    elif dimension is CoverageDimension.DEPARTMENT:
        candidates = [subject for subject in candidates if subject.tenant_id == current.tenant_id and subject.department_id != current.department_id]
    elif dimension is CoverageDimension.RELATION:
        candidates = [subject for subject in candidates if _same_scope(current, subject)]
    else:
        return None
    candidates.sort(key=lambda subject: _subject_order(current, subject))
    return candidates[0].subject_id if candidates else None


def _nearest_workflow_resource(contract: PermissionContract, rule: PermissionRule) -> str | None:
    action = next(action for action in contract.actions if action.action_id == rule.action_id)
    transition = action.workflow_transition
    if transition is None:
        return None
    resource = next(item for item in contract.resources if item.resource_id == rule.resource_id)
    candidates = [
        item
        for item in contract.resources
        if item.resource_id != resource.resource_id
        and item.resource_type == resource.resource_type
        and item.tenant_id == resource.tenant_id
        and item.department_id == resource.department_id
        and item.workflow_state not in transition.allowed_from_states
    ]
    candidates.sort(key=lambda item: (item.workflow_state, item.resource_id))
    return candidates[0].resource_id if candidates else None


def _ordinary_candidates(
    contract: PermissionContract,
    rule: PermissionRule,
    available_subjects: set[str],
    available_resources: set[str],
    available_observations: set[str],
    max_relation_depth: int,
    gaps: list[CoverageGap],
    engine_version: str,
) -> list[_Candidate]:
    subject = next(item for item in contract.subjects if item.subject_id == rule.subject_id)
    resource = next(item for item in contract.resources if item.resource_id == rule.resource_id)
    targets = ((None, rule.expectation),) + tuple((dimension, None) for dimension in rule.coverage_dimensions if dimension is not CoverageDimension.BULK)
    if rule.subject_id not in available_subjects:
        for dimension, expectation in targets:
            _gap(gaps, rule.rule_id, dimension, expectation, CoverageGapCode.MISSING_SUBJECT, "rule subject unavailable")
        return []
    if rule.resource_id not in available_resources:
        for dimension, expectation in targets:
            _gap(gaps, rule.rule_id, dimension, expectation, CoverageGapCode.MISSING_RESOURCE, "rule resource unavailable")
        return []
    if _missing_observations(rule.required_observations, available_observations):
        for dimension, expectation in targets:
            _gap(gaps, rule.rule_id, dimension, expectation, CoverageGapCode.MISSING_OBSERVER, "required observer unavailable")
        return []
    if len(rule.relation_path) > max_relation_depth:
        for dimension, expectation in targets:
            _gap(gaps, rule.rule_id, dimension, expectation, CoverageGapCode.RELATION_DEPTH_EXCEEDED, "explicit relation path exceeds max depth")
        return []
    candidates = [
        _candidate_case(
            contract=contract,
            source_rule_ids=(rule.rule_id,),
            dimensions=(),
            retention_reason=(RetentionReason.EXPLICIT_ALLOW_BASELINE if rule.expectation is PermissionExpectation.ALLOW else RetentionReason.EXPLICIT_DENY_RISK),
            priority=(1000 if rule.expectation is PermissionExpectation.DENY else 900),
            subject_id=rule.subject_id,
            action_id=rule.action_id,
            resource_ids=(rule.resource_id,),
            expectations=(rule.expectation,),
            relation_paths=(rule.relation_path,),
            context=rule.context,
            required_observations=rule.required_observations,
            engine_version=engine_version,
        )
    ]
    for dimension in rule.coverage_dimensions:
        if dimension is CoverageDimension.BULK:
            continue
        candidate_subject_id = rule.subject_id
        candidate_resource_id = rule.resource_id
        relation_path: tuple[str, ...] = ()
        if dimension is CoverageDimension.WORKFLOW:
            candidate_resource_id = _nearest_workflow_resource(contract, rule) or ""
            if not candidate_resource_id:
                _gap(gaps, rule.rule_id, dimension, None, CoverageGapCode.MISSING_RESOURCE, "no adjacent workflow resource")
                continue
        else:
            candidate_subject_id = _nearest_subject(contract, rule.subject_id, dimension) or ""
            if not candidate_subject_id:
                _gap(gaps, rule.rule_id, dimension, None, CoverageGapCode.MISSING_SUBJECT, "no adjacent subject")
                continue
            if dimension is CoverageDimension.RELATION:
                relation_path = ()
                relation_candidates = [
                    item for item in contract.subjects
                    if item.subject_id != rule.subject_id and _same_scope(subject, item)
                ]
                relation_candidates.sort(key=lambda item: _subject_order(subject, item))
                for relation_subject in relation_candidates:
                    found = _find_path(contract, relation_subject.subject_id, rule.resource_id, max_relation_depth=max_relation_depth)
                    if found is None:
                        candidate_subject_id = relation_subject.subject_id
                        break
                else:
                    _gap(gaps, rule.rule_id, dimension, None, CoverageGapCode.RELATION_UNPROVABLE, "all adjacent subjects have a valid relation")
                    continue
        if candidate_subject_id not in available_subjects:
            _gap(gaps, rule.rule_id, dimension, None, CoverageGapCode.MISSING_SUBJECT, "adjacent subject unavailable")
            continue
        if candidate_resource_id not in available_resources:
            _gap(gaps, rule.rule_id, dimension, None, CoverageGapCode.MISSING_RESOURCE, "adjacent resource unavailable")
            continue
        candidate = _candidate_case(
                contract=contract,
                source_rule_ids=(rule.rule_id,),
                dimensions=(dimension,),
                retention_reason=RetentionReason.RECENT_NEIGHBOR,
                priority=700,
                subject_id=candidate_subject_id,
                action_id=rule.action_id,
                resource_ids=(candidate_resource_id,),
                expectations=(PermissionExpectation.DENY,),
                relation_paths=(relation_path,),
                context=rule.context,
                required_observations=rule.required_observations,
                engine_version=engine_version,
                include_baseline_target=False,
            )
        candidates.append(candidate)
    return candidates


def _batch_candidates(
    contract: PermissionContract,
    rule: BatchPermissionRule,
    available_subjects: set[str],
    available_resources: set[str],
    available_observations: set[str],
    gaps: list[CoverageGap],
    engine_version: str,
    max_relation_depth: int,
) -> list[_Candidate]:
    if rule.subject_id not in available_subjects:
        _gap(gaps, rule.rule_id, CoverageDimension.BULK, None, CoverageGapCode.MISSING_SUBJECT, "batch subject unavailable")
        return []
    if _missing_observations(rule.required_observations, available_observations):
        _gap(gaps, rule.rule_id, CoverageDimension.BULK, None, CoverageGapCode.MISSING_OBSERVER, "required observer unavailable")
        return []
    if any(item.resource_id not in available_resources for item in rule.resource_expectations):
        _gap(gaps, rule.rule_id, CoverageDimension.BULK, None, CoverageGapCode.MISSING_RESOURCE, "batch resource unavailable")
        return []
    expectations = tuple(item.expectation for item in rule.resource_expectations)
    mode = (
        BatchAuthorizationMode.ALL_ALLOW
        if all(item is PermissionExpectation.ALLOW for item in expectations)
        else BatchAuthorizationMode.ALL_DENY
        if all(item is PermissionExpectation.DENY for item in expectations)
        else BatchAuthorizationMode.MIXED_AUTHORIZATION
    )
    paths = tuple(item.relation_path for item in rule.resource_expectations)
    if any(len(path) > max_relation_depth for path in paths):
        _gap(gaps, rule.rule_id, CoverageDimension.BULK, None, CoverageGapCode.RELATION_DEPTH_EXCEEDED, "batch relation path exceeds max depth")
        return []
    candidate = _candidate_case(
            contract=contract,
            source_rule_ids=(rule.rule_id,),
            dimensions=(CoverageDimension.BULK,),
            retention_reason=RetentionReason.BATCH_AUTHORIZATION,
            priority=950,
            subject_id=rule.subject_id,
            action_id=rule.action_id,
            resource_ids=tuple(item.resource_id for item in rule.resource_expectations),
            expectations=expectations,
            relation_paths=paths,
            context=rule.context,
            required_observations=rule.required_observations,
            batch_mode=mode,
            atomic=rule.atomic,
            engine_version=engine_version,
            include_baseline_target=False,
        )
    return [candidate]


def build_permission_coverage_plan(
    contract: PermissionContract,
    *,
    engine_version: str,
    seed: int,
    case_budget: int,
    available_subject_ids: tuple[str, ...] | None = None,
    available_resource_ids: tuple[str, ...] | None = None,
    available_observations: tuple[str, ...] = ("resource_state",),
    max_relation_depth: int = 8,
) -> PermissionMutationPlan:
    """在 case 预算内编译稳定覆盖计划，并把无法覆盖项保留为显式 gap。"""

    # --- 阶段：验证预算与可用身份、资源集合 ---
    if case_budget < 0:
        raise ValueError("case_budget must be non-negative")
    if max_relation_depth < 1:
        raise ValueError("max_relation_depth must be positive")
    all_subjects = {item.subject_id for item in contract.subjects}
    all_resources = {item.resource_id for item in contract.resources}
    available_subjects = all_subjects if available_subject_ids is None else set(available_subject_ids)
    available_resources = all_resources if available_resource_ids is None else set(available_resource_ids)
    gaps: list[CoverageGap] = []
    raw: list[_Candidate] = []
    # --- 阶段：生成普通关系变异与批量变异候选 ---
    for rule in contract.rules:
        raw.extend(_ordinary_candidates(contract, rule, available_subjects, available_resources, set(available_observations), max_relation_depth, gaps, engine_version))
    for rule in contract.batch_rules:
        raw.extend(_batch_candidates(contract, rule, available_subjects, available_resources, set(available_observations), gaps, engine_version, max_relation_depth))
    def sort_key(item: _Candidate) -> tuple[Any, ...]:
        return (
            -item.priority,
            permission_model_sha256({"seed": seed, "engine_version": engine_version, "candidate": item.case.fingerprint}),
            item.case.fingerprint,
            item.source_rule_ids,
        )

    # --- 阶段：稳定排序、语义去重并按预算截取 ---
    raw.sort(key=sort_key)
    unique: dict[str, _Candidate] = {}
    eliminated: list[EliminatedCandidate] = []
    for item in raw:
        previous = unique.get(item.case.fingerprint)
        if previous is not None:
            winner, loser = (item, previous) if item.priority > previous.priority else (previous, item)
            merged_sources = tuple(sorted(set(previous.source_rule_ids + item.source_rule_ids)))
            merged_dimensions = tuple(sorted(set(previous.dimensions + item.dimensions), key=lambda value: value.value))
            unique[item.case.fingerprint] = _Candidate(
                semantic=winner.semantic,
                source_rule_ids=merged_sources,
                dimensions=merged_dimensions,
                retention_reason=winner.retention_reason,
                priority=winner.priority,
                case=winner.case.model_copy(update={"source_rule_ids": merged_sources, "dimensions": merged_dimensions}),
                target_keys=tuple(sorted(set(previous.target_keys + item.target_keys), key=str)),
            )
            eliminated.append(
                EliminatedCandidate(
                    candidate_fingerprint=item.case.fingerprint,
                    source_rule_ids=loser.source_rule_ids,
                    reason=EliminatedReason.DUPLICATE_SEMANTICS,
                )
            )
            continue
        unique[item.case.fingerprint] = item
    ordered = sorted(unique.values(), key=sort_key)
    retained = ordered[:case_budget]
    for item in ordered[case_budget:]:
        eliminated.append(
            EliminatedCandidate(
                candidate_fingerprint=item.case.fingerprint,
                source_rule_ids=item.source_rule_ids,
                reason=EliminatedReason.BUDGET_EXCEEDED,
            )
        )
        for rule_id, dimension, expectation in item.target_keys:
            _gap(gaps, rule_id, dimension, expectation, CoverageGapCode.BUDGET_EXCEEDED, "case budget exceeded")
    cases = tuple(item.case for item in retained)
    # --- 阶段：为每条规则投影可解释覆盖记录与缺口 ---
    coverage: list[CoverageRecord] = []
    for rule in (*contract.rules, *contract.batch_rules):
        targets = ((CoverageDimension.BULK, None),) if isinstance(rule, BatchPermissionRule) else tuple(
            [(None, rule.expectation)] + [(dimension, None) for dimension in rule.coverage_dimensions]
        )
        for dimension, expectation in targets:
            case_ids = tuple(item.case.case_id for item in retained if (rule.rule_id, dimension, expectation) in item.target_keys)
            rule_gaps = tuple(
                gap.code for gap in gaps
                if gap.rule_id == rule.rule_id and gap.dimension is dimension and gap.expectation is expectation
            )
            coverage.append(
                CoverageRecord(
                    rule_id=rule.rule_id,
                    expectation=expectation,
                    dimension=dimension,
                    status=CoverageStatus.COVERED if case_ids and not rule_gaps else CoverageStatus.GAP,
                    case_ids=case_ids,
                    gap_codes=tuple(sorted(set(rule_gaps), key=lambda code: code.value)),
                )
            )
    coverage = sorted(coverage, key=lambda item: (item.rule_id, item.dimension.value if item.dimension else "", item.expectation.value if item.expectation else ""))
    gaps = sorted(gaps, key=lambda item: (item.rule_id, item.dimension.value if item.dimension else "", item.expectation.value if item.expectation else "", item.code.value, item.detail))
    eliminated = sorted(eliminated, key=lambda item: (item.candidate_fingerprint, item.reason.value, item.source_rule_ids))
    body = {
        "contract_fingerprint": permission_model_sha256(contract),
        "seed": seed,
        "engine_version": engine_version,
        "case_budget": case_budget,
        "cases": cases,
        "coverage": tuple(coverage),
        "gaps": tuple(gaps),
        "eliminated": tuple(eliminated),
    }
    plan_fingerprint = permission_model_sha256(body)
    return PermissionMutationPlan(
        plan_id=f"plan-{plan_fingerprint[:32]}",
        plan_fingerprint=plan_fingerprint,
        contract_fingerprint=body["contract_fingerprint"],
        seed=seed,
        engine_version=engine_version,
        case_budget=case_budget,
        candidate_count=len(raw),
        retained_count=len(cases),
        cases=cases,
        coverage=tuple(coverage),
        gaps=tuple(gaps),
        eliminated=tuple(eliminated),
    )
