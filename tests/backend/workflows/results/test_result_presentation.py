# 验证唯一结果业务投影只翻译已发布三态事实，不重算安全结论。

from __future__ import annotations

from types import SimpleNamespace

import pytest

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import CaseVerdict, RunLifecycle, RunVerdict
from product.backend.core.permission_intent import PermissionIntentRelation, ProtectedEffect
from product.backend.core.repair import (
    RepairContractReference,
    RepairRequirementView,
    RepairVerification,
    RepairVerificationStatus,
)
from product.backend.core.verification.breakpoints import (
    BreakpointPrecision,
    BreakpointResult,
    BreakpointType,
)
from product.backend.core.verification.continuity import (
    AuthorizationContinuityAssessment,
    AuthorizationContinuityState,
    AuthorizationEffectReference,
)
from product.backend.core.verification.facts import (
    ExecutionOutcome,
    ObservedEffect,
    TemporalClosure,
)
from product.backend.core.verification.permissions import (
    PermissionExpectation,
    SecurityEffectKind,
)
from product.backend.core.verification.trace import ExecutionTrace, TraceEventKind
from product.backend.workflows.results.presentation import (
    _actual_identity,
    _breakpoint_detail,
    _claim_boundary_with_repair,
    ResultPresentationBuilder,
    build_result_presentation,
)
from product.protocols import ObservationCompleteness, ObserverOutcomeStatus, ObserverType
from product.protocols.execution_request import (
    ChangeVerificationContext,
    PermissionPolicySnapshotEntry,
    build_permission_policy_snapshot,
)


RUN_ID = "run_" + "1" * 32
PROJECT_ID = "presentation-project"
FINDING_ID = "finding_" + "2" * 32
EVIDENCE_ID = "evidence_" + "3" * 32
ACTION_ID = "modify-document"
EFFECT_ID = "effect-document"
RESOURCE_ID = "owner-document"
REQUIREMENT_ID = "resource_state"
OBSERVER_ID = "owner-observer"
CASE_ID = "case-presentation"


def _orphan_continuity() -> AuthorizationContinuityAssessment:
    effect = AuthorizationEffectReference(
        effect_id=EFFECT_ID,
        resource_id=RESOURCE_ID,
    )
    return AuthorizationContinuityAssessment(
        case_id=CASE_ID,
        action_id=ACTION_ID,
        state=AuthorizationContinuityState.ORPHAN_EFFECT_CONFIRMED,
        protected_effects=(effect,),
        confirmed_effects=(effect,),
        reason_codes=("DENY_PROTECTED_EFFECT_CONFIRMED",),
    )
def _view(
    verdict: RunVerdict | None,
    case_verdict: CaseVerdict,
    *,
    lifecycle: RunLifecycle = RunLifecycle.COMPLETED,
    outcome: ExecutionOutcome = ExecutionOutcome.ACCEPTED,
    effect: ObservedEffect = ObservedEffect.ABSENT,
    coverage_gap_count: int = 0,
):
    evidence = SimpleNamespace(
        evidence_id=EVIDENCE_ID,
        verdict=case_verdict,
        case_snapshot=SimpleNamespace(
            case_id=CASE_ID,
            subject_id="member-subject",
            action_id=ACTION_ID,
            resource_ids=(RESOURCE_ID,),
            expectations=(PermissionExpectation.DENY,),
        ),
        execution_fact=SimpleNamespace(outcome=outcome),
        security_effect_facts=(SimpleNamespace(state=effect),),
        requirement_bindings=(
            SimpleNamespace(
                requirement_id=REQUIREMENT_ID,
                observer_id=OBSERVER_ID,
                observer_type=ObserverType.OWNER_API,
            ),
        ),
        observation_facts=(
            SimpleNamespace(
                requirement_id=REQUIREMENT_ID,
                resource_id=RESOURCE_ID,
                effect=effect,
                complete=effect is not ObservedEffect.UNKNOWN,
                reliable=effect is not ObservedEffect.UNKNOWN,
                correlated=effect is not ObservedEffect.UNKNOWN,
                temporal_closure=(
                    TemporalClosure.CLOSED
                    if effect is not ObservedEffect.UNKNOWN
                    else TemporalClosure.OPEN
                ),
            ),
        ),
        outcomes=(
            SimpleNamespace(
                observer_id=OBSERVER_ID,
                required=True,
                status=(
                    ObserverOutcomeStatus.AVAILABLE
                    if effect is not ObservedEffect.UNKNOWN
                    else ObserverOutcomeStatus.INCONCLUSIVE
                ),
            ),
        ),
        observations=(),
    )
    result = SimpleNamespace(
        verdict=verdict,
        evidence=(evidence,),
        coverage_gap_count=coverage_gap_count,
    )
    return SimpleNamespace(
        run=SimpleNamespace(
            run_id=RUN_ID,
            project_id=PROJECT_ID,
            lifecycle=lifecycle,
        ),
        publication=SimpleNamespace(result=result),
    )


def _snapshot(*, include_binding: bool = True):
    return SimpleNamespace(
        project_name="文档系统",
        contract=SimpleNamespace(
            actions=(SimpleNamespace(action_id=ACTION_ID, effect_ids=(EFFECT_ID,)),),
            effects=(
                SimpleNamespace(
                    effect_id=EFFECT_ID,
                    kind=SecurityEffectKind.STATE_MUTATION,
                    resource_type="document",
                ),
            ),
        ),
        effect_bindings=(
            SimpleNamespace(
                effect_id=EFFECT_ID,
                required_channels=(REQUIREMENT_ID,),
                corroborating_channels=(),
            ),
        ),
        observer_bindings=(
            SimpleNamespace(
                requirement_id=REQUIREMENT_ID,
                observer_id=OBSERVER_ID,
                observer_type=ObserverType.OWNER_API,
            ),
        ),
        identities=(
            SimpleNamespace(identity_id="member-account", label="成员测试账号"),
        ),
        subject_bindings=(
            SimpleNamespace(
                subject_id="member-subject",
                identity_id="member-account",
            ),
        )
        if include_binding
        else (),
    )


def _finding(verdict: CaseVerdict, *, status: str = "APPEARED") -> list[dict]:
    return [
        {
            "finding": {
                "finding_id": FINDING_ID,
                "identity": {
                    "subject_class": ["role:member"],
                    "action": "modify",
                    "resource_class": ["type:document"],
                    "resource_relation": ["relation:owns-document:OWNS"],
                },
            },
            "occurrence": {
                "status": status,
                "verdict": verdict.value,
                "severity": "critical",
                "evidence_refs": [EVIDENCE_ID],
            },
        }
    ]


def _six_source_facts(*, unavailable: bool = False):
    source_types = tuple(ObserverType)
    requirements = tuple(f"source_{index}" for index in range(len(source_types)))
    observer_ids = tuple(f"observer-{index}" for index in range(len(source_types)))
    effects = (
        ObservedEffect.CONFIRMED,
        ObservedEffect.ABSENT,
        ObservedEffect.UNKNOWN,
        ObservedEffect.CONFIRMED,
        ObservedEffect.CONFIRMED,
        ObservedEffect.UNKNOWN,
    )
    if unavailable:
        effects = tuple(ObservedEffect.UNKNOWN for _ in source_types)
    bindings = tuple(
        SimpleNamespace(
            requirement_id=requirement_id,
            observer_id=observer_id,
            observer_type=observer_type,
        )
        for requirement_id, observer_id, observer_type in zip(
            requirements,
            observer_ids,
            source_types,
            strict=True,
        )
    )
    facts = tuple(
        SimpleNamespace(
            requirement_id=requirement_id,
            resource_id=RESOURCE_ID,
            effect=effect,
            complete=effect is not ObservedEffect.UNKNOWN,
            reliable=effect is not ObservedEffect.UNKNOWN,
            correlated=effect is not ObservedEffect.UNKNOWN,
            temporal_closure=(
                TemporalClosure.CLOSED
                if effect is not ObservedEffect.UNKNOWN
                else TemporalClosure.OPEN
            ),
        )
        for requirement_id, effect in zip(requirements, effects, strict=True)
    )
    outcomes = tuple(
        SimpleNamespace(
            observer_id=observer_id,
            required=index in {0, 5},
            status=(
                ObserverOutcomeStatus.AVAILABLE
                if effect is not ObservedEffect.UNKNOWN
                else ObserverOutcomeStatus.INCONCLUSIVE
            ),
        )
        for index, (observer_id, effect) in enumerate(
            zip(observer_ids, effects, strict=True)
        )
    )
    snapshot = _snapshot()
    snapshot.observer_bindings = bindings
    snapshot.effect_bindings = (
        SimpleNamespace(
            effect_id=EFFECT_ID,
            required_channels=(requirements[0], requirements[5]),
            corroborating_channels=requirements[1:5],
        ),
    )
    return requirements, bindings, facts, outcomes, snapshot


def test_block_presentation_preserves_403_with_real_change_as_permission_problem() -> None:
    policy = build_permission_policy_snapshot(
        PROJECT_ID,
        7,
        (
            PermissionPolicySnapshotEntry(
                intent_id="pin_" + "4" * 32,
                revision=3,
                intent_hash="5" * 64,
                binding_fingerprint="6" * 64,
                expectation=PermissionExpectation.DENY,
                relation=PermissionIntentRelation.OTHER_ROLE,
                subject_display_name="普通成员",
                action_display_name="创建任务",
                resource_owner_display_name="项目负责人",
                protected_effects=(
                    ProtectedEffect(
                        kind=SecurityEffectKind.STATE_MUTATION,
                        resource_type="document",
                        business_label="负责人文档已被修改",
                    ),
                ),
                action_candidate_id="action_" + "7" * 32,
                subject_test_identity_id="tid_" + "8" * 32,
            ),
        ),
    )
    result = build_result_presentation(
        _view(
            RunVerdict.BLOCK,
            CaseVerdict.VULNERABLE,
            outcome=ExecutionOutcome.DENIED,
            effect=ObservedEffect.CONFIRMED,
            coverage_gap_count=2,
        ),
        _snapshot(),
        _finding(CaseVerdict.VULNERABLE),
        permission_policy=policy,
        change_context=ChangeVerificationContext(
            change_id="chg_" + "7" * 32,
            impact_fingerprint="8" * 64,
            required_intent_ids=("pin_" + "4" * 32,),
        ),
    )

    assert result.headline == "发现权限问题"
    assert result.policy_epoch == 7
    assert result.policy_fingerprint == policy.policy_fingerprint
    assert result.relevant_intents[0].model_dump(mode="json") == {
        "intent_id": "pin_" + "4" * 32,
        "revision": 3,
        "intent_hash": "5" * 64,
        "display_label": "P-001",
        "expectation": "DENY",
        "business_statement": (
            "普通成员不可以对项目负责人的资源执行“创建任务”（资源属于其他权限组）。"
            "受保护业务后果“负责人文档已被修改”不得发生。"
        ),
    }
    assert result.change_verification is not None
    assert result.change_verification.change_id == "chg_" + "7" * 32
    assert result.change_verification.required_intents == result.relevant_intents
    assert "source_fingerprint" not in result.model_dump(mode="json")[
        "change_verification"
    ]
    assert result.checked_count == 1
    assert result.problem_count == 1
    assert result.uncovered_count == 2
    assert result.execution_problem is None
    assert result.issues[0].title == "成员账号不应对文档执行修改"
    assert result.issues[0].surface_result == "页面或接口显示已拒绝"
    assert result.issues[0].actual_result == "真实资源已经发生变化"
    assert "表面拒绝没有阻止真实副作用" in result.issues[0].explanation
    assert result.issues[0].planned_identity_id == "member-account"
    assert result.issues[0].planned_identity_label == "成员测试账号"
    assert result.issues[0].actual_identity_status == "UNAVAILABLE"
    assert result.issues[0].actual_identity_label is None
    assert result.issues[0].claim_boundary.model_dump(mode="json") == {
        "surface_response_status": "DENIED",
        "business_effect_status": "CONFIRMED",
        "actual_identity_status": "UNAVAILABLE",
        "breakpoint_precision": None,
        "repair_status": None,
        "supported_statement": (
            "计划使用成员测试账号凭据的实验中，负责人文档已被修改。"
        ),
        "unsupported_statements": [
            "不能把表面拒绝直接解释为后台副作用或最终业务后果未发生。",
            "不能宣称服务器已经独立确认实际执行主体。",
            "不能宣称已经定位到具体权限断裂环节。",
            "当前没有已发布的修复复验结论，不能宣称修复已经通过。",
        ],
    }
    surface = result.issues[0].evidence_explanations[0]
    assert surface.source == "执行表面响应"
    assert "不能单独证明后台副作用" in surface.does_not_prove
    assert "当前 Run" in surface.relevance
    owner = next(
        item
        for item in result.issues[0].evidence_explanations
        if item.source == ObserverType.OWNER_API.value
    )
    assert "负责人文档已被修改" in owner.proves
    assert owner.component is owner.observed_at_us is None


def test_repair_status_only_strengthens_claim_boundary_after_formal_verification() -> None:
    result = build_result_presentation(
        _view(
            RunVerdict.BLOCK,
            CaseVerdict.VULNERABLE,
            outcome=ExecutionOutcome.DENIED,
            effect=ObservedEffect.CONFIRMED,
        ),
        _snapshot(),
        _finding(CaseVerdict.VULNERABLE),
    )
    boundary = result.issues[0].claim_boundary

    verified = _claim_boundary_with_repair(
        boundary,
        RepairVerificationStatus.VERIFIED,
    )
    inconclusive = _claim_boundary_with_repair(
        boundary,
        RepairVerificationStatus.INCONCLUSIVE,
    )

    assert verified.repair_status is RepairVerificationStatus.VERIFIED
    assert all("修复" not in item for item in verified.unsupported_statements)
    assert inconclusive.repair_status is RepairVerificationStatus.INCONCLUSIVE
    assert "修复复验证据不足" in inconclusive.unsupported_statements[-1]


def test_formal_repair_run_projects_contract_and_status_on_the_stable_finding() -> None:
    source_run_id = "run_" + "9" * 32
    reference = RepairContractReference(
        source_run_id=source_run_id,
        source_finding_id=FINDING_ID,
        repair_fingerprint="8" * 64,
    )
    verification = RepairVerification(
        reference=reference,
        verification_run_id=RUN_ID,
        status=RepairVerificationStatus.VERIFIED,
        message="三条修复路径均已验证。",
        reason_codes=("REPAIR_REQUIREMENTS_SATISFIED",),
    )
    requirement = RepairRequirementView(
        reference=reference,
        must_disappear="原违规后果必须消失。",
        must_remain="两条合法业务路径必须保留。",
        must_not_change=("原权限要求", "关键证据标准"),
    )
    policy = build_permission_policy_snapshot(
        PROJECT_ID,
        7,
        (
            PermissionPolicySnapshotEntry(
                intent_id="pin_" + "4" * 32,
                revision=3,
                intent_hash="5" * 64,
                binding_fingerprint="6" * 64,
                expectation=PermissionExpectation.DENY,
                relation=PermissionIntentRelation.OTHER_ROLE,
                subject_display_name="普通成员",
                action_display_name="修改文档",
                resource_owner_display_name="项目负责人",
                protected_effects=(
                    ProtectedEffect(
                        kind=SecurityEffectKind.STATE_MUTATION,
                        resource_type="document",
                        business_label="负责人文档被修改",
                    ),
                ),
                action_candidate_id="action_" + "7" * 32,
                subject_test_identity_id="tid_" + "8" * 32,
            ),
        ),
    )
    view = _view(
        RunVerdict.PASS,
        CaseVerdict.SAFE,
        outcome=ExecutionOutcome.DENIED,
        effect=ObservedEffect.ABSENT,
    )

    class Reader:
        @staticmethod
        def read(run_id: str):
            assert run_id == RUN_ID
            return view

        @staticmethod
        def execution_request(current):
            assert current is view
            return SimpleNamespace(
                project_snapshot=_snapshot(),
                permission_policy=policy,
                change_context=None,
            )

    class Findings:
        @staticmethod
        def findings_for_run(run_id: str):
            assert run_id == RUN_ID
            return _finding(CaseVerdict.SAFE, status="DISAPPEARED")

    class Repairs:
        @staticmethod
        def verify_run(run_id: str):
            assert run_id == RUN_ID
            return verification

        @staticmethod
        def requirement(run_id: str, finding_id: str):
            assert (run_id, finding_id) == (source_run_id, FINDING_ID)
            return requirement

    result = ResultPresentationBuilder(Reader(), Findings(), Repairs()).build(RUN_ID)

    assert result.repair_verification is verification
    assert result.issues[0].repair_requirement is requirement
    assert result.issues[0].claim_boundary.repair_status is RepairVerificationStatus.VERIFIED
    assert all("修复" not in item for item in result.issues[0].claim_boundary.unsupported_statements)


@pytest.mark.parametrize(
    ("run_verdict", "case_verdict", "headline", "conclusion"),
    (
        (RunVerdict.PASS, CaseVerdict.SAFE, "当前检查范围未发现确认问题", "符合预期"),
        (RunVerdict.INCONCLUSIVE, CaseVerdict.INCONCLUSIVE, "证据不足", "证据不足"),
    ),
)
def test_pass_and_inconclusive_use_the_same_deterministic_business_view(
    run_verdict: RunVerdict,
    case_verdict: CaseVerdict,
    headline: str,
    conclusion: str,
) -> None:
    effect = ObservedEffect.ABSENT if case_verdict is CaseVerdict.SAFE else ObservedEffect.UNKNOWN
    result = build_result_presentation(
        _view(run_verdict, case_verdict, effect=effect),
        _snapshot(),
        _finding(case_verdict, status="PRESENT"),
    )

    assert result.headline == headline
    assert result.issues[0].conclusion == conclusion
    assert result.execution_problem is None
    if run_verdict is RunVerdict.PASS:
        assert "不代表应用绝对安全" in result.scope_statement
    else:
        assert "不代表安全，也不代表已经确认漏洞" in result.scope_statement


def test_only_failed_or_cancelled_lifecycle_creates_execution_problem() -> None:
    failed = build_result_presentation(
        _view(
            None,
            CaseVerdict.INCONCLUSIVE,
            lifecycle=RunLifecycle.FAILED,
            effect=ObservedEffect.UNKNOWN,
        ),
        _snapshot(),
        _finding(CaseVerdict.INCONCLUSIVE),
    )
    block = build_result_presentation(
        _view(
            RunVerdict.BLOCK,
            CaseVerdict.VULNERABLE,
            effect=ObservedEffect.CONFIRMED,
        ),
        _snapshot(),
        _finding(CaseVerdict.VULNERABLE),
    )

    assert failed.execution_problem == "检查执行失败，未形成可用安全结论。"
    assert block.execution_problem is None


def test_missing_planned_identity_binding_fails_closed() -> None:
    with pytest.raises(JiejianError) as captured:
        build_result_presentation(
            _view(RunVerdict.BLOCK, CaseVerdict.VULNERABLE),
            _snapshot(include_binding=False),
            _finding(CaseVerdict.VULNERABLE),
        )

    assert captured.value.code == ErrorCode.ARTIFACT_FENCE.value


def test_six_sources_use_frozen_roles_stable_order_and_published_fact_status() -> None:
    view = _view(
        RunVerdict.BLOCK,
        CaseVerdict.VULNERABLE,
        outcome=ExecutionOutcome.DENIED,
        effect=ObservedEffect.CONFIRMED,
    )
    _, bindings, facts, outcomes, snapshot = _six_source_facts()
    evidence = view.publication.result.evidence[0]
    evidence.requirement_bindings = bindings
    evidence.observation_facts = facts
    evidence.outcomes = outcomes

    result = build_result_presentation(
        view,
        snapshot,
        _finding(CaseVerdict.VULNERABLE),
    )

    sources = result.issues[0].evidence_sources
    assert [item.observer_type for item in sources] == list(ObserverType)
    assert [item.label for item in sources] == [
        "目标业务状态",
        "只读数据库",
        "结构化审计记录",
        "后台任务",
        "消息通道",
        "最终对象/文件",
    ]
    assert [item.role for item in sources] == [
        "KEY",
        "SUPPORTING",
        "SUPPORTING",
        "SUPPORTING",
        "SUPPORTING",
        "KEY",
    ]
    assert [item.status for item in sources] == [
        "FOUND",
        "NOT_FOUND",
        "UNAVAILABLE",
        "FOUND",
        "FOUND",
        "UNAVAILABLE",
    ]
    assert all(item.evidence_refs == (EVIDENCE_ID,) for item in sources)
    queue = next(
        item
        for item in result.issues[0].evidence_explanations
        if item.source == ObserverType.AZURE_QUEUE_PEEK.value
    )
    assert "与本轮关联的队列消息" in queue.proves
    assert "负责人文档已被修改" not in queue.proves
    assert "不能单独证明 Worker 已执行" in queue.does_not_prove
    assert "最终对象已经生成" in queue.does_not_prove
    assert result.verdict is RunVerdict.BLOCK
    assert result.issues[0].verdict.value == CaseVerdict.VULNERABLE.value
    assert result.issues[0].actual_identity_status == "UNAVAILABLE"


def test_source_availability_translation_never_recomputes_verdict() -> None:
    view = _view(
        RunVerdict.BLOCK,
        CaseVerdict.VULNERABLE,
        effect=ObservedEffect.CONFIRMED,
    )
    _, bindings, facts, outcomes, snapshot = _six_source_facts(unavailable=True)
    evidence = view.publication.result.evidence[0]
    evidence.requirement_bindings = bindings
    evidence.observation_facts = facts
    evidence.outcomes = outcomes

    result = build_result_presentation(
        view,
        snapshot,
        _finding(CaseVerdict.VULNERABLE),
    )

    assert {item.status for item in result.issues[0].evidence_sources} == {
        "UNAVAILABLE"
    }
    assert result.verdict is RunVerdict.BLOCK
    assert result.issues[0].verdict.value == CaseVerdict.VULNERABLE.value


def test_published_audit_trace_exposes_unified_identity_and_diagnosis(
    monkeypatch,
) -> None:
    semantic_keys = (
        "request_received",
        "server_identity_resolved",
        "export_request_created",
        "authorization_decided",
        "export_message_sent",
        "export_job_started",
        "archive_generated",
        "export_job_completed",
    )
    kinds = (
        "ENTRY",
        "IDENTITY",
        "PERSISTENT_EFFECT",
        "AUTHORIZATION",
        "MESSAGE",
        "DELEGATION",
        "FINAL_EFFECT",
        "FINAL_EFFECT",
    )
    records = [
        {
            "event_id": f"trace-{index}",
            "parent_event_id": f"trace-{index - 1}" if index > 1 else None,
            "case_tag": CASE_ID,
            "task_id": "task-export",
            "event_type": semantic_key,
            "semantic_key": semantic_key,
            "sequence": index,
            "resource_id": RESOURCE_ID,
            "kind": kinds[index - 1],
            "subject_id": "bob",
            "actor_id": "export-worker" if index >= 6 else "bob",
            "authorization_decision": "DENY" if semantic_key == "authorization_decided" else None,
            "source_component": "export-worker" if index >= 6 else "collaboration-server",
            "source_location": "worker:export" if index >= 6 else "api:/projects/export",
            "recorded_at_us": 1_000 + index,
        }
        for index, semantic_key in enumerate(semantic_keys, start=1)
    ]
    for index, record in enumerate(records, start=1):
        if index >= 5:
            record["origin_authorization_event_id"] = "trace-4"
        if index >= 6:
            record["delegated_from_event_id"] = f"trace-{index - 1}"
    view = _view(
        RunVerdict.BLOCK,
        CaseVerdict.VULNERABLE,
        effect=ObservedEffect.CONFIRMED,
    )
    view.publication.result.evidence[0].observations = (
        SimpleNamespace(
            observer_type=ObserverType.STRUCTURED_AUDIT_LOG,
            completeness=ObservationCompleteness.COMPLETE,
            state=SimpleNamespace(canonical_data={"records": records}),
        ),
    )
    original_verdict = view.publication.result.verdict

    snapshot = _snapshot()
    case = view.publication.result.evidence[0].case_snapshot
    snapshot.differential_plan = SimpleNamespace(
        twins=(SimpleNamespace(allow_case=case, deny_case=case),)
    )
    breakpoint = BreakpointResult(
        case_id=CASE_ID,
        action_id=ACTION_ID,
        breakpoint_type=BreakpointType.AUTHORIZATION_LATE,
        precision=BreakpointPrecision.EXACT,
        last_known_good_event_id="trace-2",
        first_violation_event_id="trace-3",
        continuity=_orphan_continuity(),
        orphan_effect_ids=(EFFECT_ID,),
        downstream_event_ids=tuple(f"trace-{index}" for index in range(4, 9)),
        evidence_refs=(EVIDENCE_ID,),
        reason_codes=("BREAKPOINT_AUTHORIZATION_LATE",),
    )
    monkeypatch.setattr(
        "product.backend.workflows.results.presentation.BreakpointLocator.locate",
        lambda *_args, **_kwargs: breakpoint,
    )

    result = build_result_presentation(
        view,
        snapshot,
        _finding(CaseVerdict.VULNERABLE),
    )

    trace = result.execution_traces[0]
    assert trace.complete is True
    assert trace.events[0].subject_id == trace.events[0].actor_id == "bob"
    assert trace.events[-1].subject_id == "bob"
    assert trace.events[-1].actor_id == "export-worker"
    assert result.issues[0].actual_identity_status == "CONFIRMED"
    assert result.issues[0].actual_identity_id == "bob"
    assert result.issues[0].actual_identity_label == "bob"
    diagnosis = result.issues[0].diagnosis
    assert diagnosis is not None
    assert diagnosis.breakpoint_type is BreakpointType.AUTHORIZATION_LATE
    assert diagnosis.precision is BreakpointPrecision.EXACT
    assert diagnosis.first_violation_event_id == "trace-3"
    assert diagnosis.range_start_event_id is None
    assert diagnosis.range_end_event_id is None
    assert tuple(item.kind for item in diagnosis.minimal_witness) == (
        "PERMISSION_REQUIREMENT",
        "ACTUAL_IDENTITY",
        "PROTECTED_EFFECT",
        "AUTHORIZATION_CONTINUITY",
        "BREAKPOINT",
        "AMPLIFIERS",
        "CONFIRMED_IMPACT",
    )
    assert diagnosis.minimal_witness[1].detail == result.issues[0].actual_identity_label
    assert diagnosis.minimal_witness[2].event_id == "trace-8"
    assert "找不到符合原权限要求的合法授权来源" in diagnosis.minimal_witness[3].detail
    assert diagnosis.minimal_witness[4].event_id == "trace-3"
    assert diagnosis.minimal_witness[6].event_id == "trace-8"
    assert {item.event_id for item in diagnosis.confirmed_impacts} == {
        f"trace-{index}" for index in range(4, 9)
    }
    assert all(
        item.event_id in {event.event_id for event in trace.events}
        for item in diagnosis.confirmed_impacts
    )
    assert result.verdict is original_verdict is RunVerdict.BLOCK
    assert view.publication.result.verdict is RunVerdict.BLOCK
    boundary = result.issues[0].claim_boundary
    assert boundary.actual_identity_status == "CONFIRMED"
    assert boundary.breakpoint_precision is BreakpointPrecision.EXACT
    identity_explanation = next(
        item
        for item in result.issues[0].evidence_explanations
        if item.source == "ExecutionTrace"
    )
    assert identity_explanation.component == "collaboration-server"
    assert identity_explanation.observed_at_us == 1_002
    breakpoint_explanation = next(
        item
        for item in result.issues[0].evidence_explanations
        if item.source == "BreakpointLocator"
    )
    assert breakpoint_explanation.component == "collaboration-server"
    assert breakpoint_explanation.observed_at_us == 1_003

    evidence = view.publication.result.evidence[0]
    partial_trace = trace.model_copy(
        update={"complete": False, "reason_codes": ("TRACE_AUDIT_INCOMPLETE",)}
    )
    assert _actual_identity(
        evidence,
        {(trace.case_id, trace.action_id): partial_trace},
    ) == ("UNAVAILABLE", None, None)

    second_identity = trace.events[1].model_copy(
        update={
            "event_id": "trace-conflicting-identity",
            "parent_event_ids": ("trace-2",),
            "subject_id": "alice",
            "recorded_at_us": 1_020,
        }
    )
    conflict_trace = ExecutionTrace(
        case_id=trace.case_id,
        action_id=trace.action_id,
        planned_subject_id=trace.planned_subject_id,
        events=(*trace.events, second_identity),
        complete=True,
    )
    assert _actual_identity(
        evidence,
        {(trace.case_id, trace.action_id): conflict_trace},
    ) == ("UNAVAILABLE", None, None)


def test_breakpoint_precision_copy_is_explicit_in_user_text() -> None:
    by_id = {
        "trace-start": SimpleNamespace(kind=TraceEventKind.IDENTITY),
        "trace-end": SimpleNamespace(kind=TraceEventKind.PERSISTENT_EFFECT),
    }
    ranged = BreakpointResult(
        case_id=CASE_ID,
        action_id=ACTION_ID,
        breakpoint_type=BreakpointType.AUTHORIZATION_LATE,
        precision=BreakpointPrecision.RANGE,
        last_known_good_event_id="trace-start",
        range_start_event_id="trace-start",
        range_end_event_id="trace-end",
        continuity=_orphan_continuity(),
        orphan_effect_ids=(EFFECT_ID,),
        evidence_refs=(EVIDENCE_ID,),
        reason_codes=("BREAKPOINT_RANGE_ONLY",),
    )
    violation = BreakpointResult(
        case_id=CASE_ID,
        action_id=ACTION_ID,
        breakpoint_type=BreakpointType.AUTHORIZATION_LATE,
        precision=BreakpointPrecision.VIOLATION_ONLY,
        first_violation_event_id="trace-violation",
        continuity=_orphan_continuity(),
        orphan_effect_ids=(EFFECT_ID,),
        evidence_refs=(EVIDENCE_ID,),
        reason_codes=("VIOLATION_ONLY",),
    )

    assert _breakpoint_detail(ranged, by_id) == (
        "断裂发生在 身份确认 与 持久化后果 之间"
    )
    assert _breakpoint_detail(violation, by_id) == (
        "违规已确认，但当前证据不足以进一步定位"
    )


def test_non_audit_confirmed_effect_keeps_orphan_story_and_original_verdict(
    monkeypatch,
) -> None:
    view = _view(
        RunVerdict.BLOCK,
        CaseVerdict.VULNERABLE,
        effect=ObservedEffect.CONFIRMED,
    )
    snapshot = _snapshot()
    case = view.publication.result.evidence[0].case_snapshot
    snapshot.differential_plan = SimpleNamespace(
        twins=(SimpleNamespace(allow_case=case, deny_case=case),)
    )
    breakpoint = BreakpointResult(
        case_id=CASE_ID,
        action_id=ACTION_ID,
        breakpoint_type=None,
        precision=BreakpointPrecision.VIOLATION_ONLY,
        continuity=_orphan_continuity(),
        orphan_effect_ids=(EFFECT_ID,),
        evidence_refs=(EVIDENCE_ID,),
        reason_codes=(
            "CONFIRMED_ORPHAN_EFFECT",
            "PROTECTED_EFFECT_EVENT_UNAVAILABLE",
            "VIOLATION_ONLY",
        ),
    )
    monkeypatch.setattr(
        "product.backend.workflows.results.presentation.BreakpointLocator.locate",
        lambda *_args, **_kwargs: breakpoint,
    )

    result = build_result_presentation(
        view,
        snapshot,
        _finding(CaseVerdict.VULNERABLE),
    )

    diagnosis = result.issues[0].diagnosis
    assert diagnosis is not None
    assert result.execution_traces[0].complete is False
    assert diagnosis.continuity_state is AuthorizationContinuityState.ORPHAN_EFFECT_CONFIRMED
    assert diagnosis.precision is BreakpointPrecision.VIOLATION_ONLY
    assert diagnosis.first_violation_event_id is None
    assert diagnosis.range_start_event_id is None
    assert diagnosis.range_end_event_id is None
    assert "找不到符合原权限要求的合法授权来源" in diagnosis.summary
    assert "当前证据不足以进一步定位" in diagnosis.summary
    assert result.verdict is view.publication.result.verdict is RunVerdict.BLOCK
