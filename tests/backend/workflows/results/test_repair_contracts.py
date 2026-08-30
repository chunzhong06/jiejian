# 验证 RepairContract 只从已发布事实重建，并以原考题、合法控制和证据标准独立复验。

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

from product.backend.core.errors import JiejianError
from product.backend.core.lifecycle import CaseVerdict, RunVerdict
from product.backend.core.permission_intent import PermissionIntentRelation
from product.backend.core.repair import RepairVerificationStatus
from product.backend.core.verification.breakpoints import (
    BreakpointPrecision,
    BreakpointType,
)
from product.backend.core.verification.continuity import (
    AuthorizationContinuityState,
)
from product.backend.core.verification.differential import TwinExecutionRole
from product.backend.core.verification.facts import ObservedEffect
from product.backend.core.verification.permissions import PermissionExpectation
from product.backend.workflows.results import repair as repair_module
from product.backend.workflows.results.repair import RepairContractService
from product.protocols.execution_request import (
    PermissionPolicySnapshot,
    PermissionPolicySnapshotEntry,
    build_permission_policy_snapshot,
)


PROJECT_ID = "repair-project"
SOURCE_RUN_ID = "run_" + "1" * 32
VERIFY_RUN_ID = "run_" + "2" * 32
FINDING_ID = "finding_" + "3" * 32
ACTION_ID = "action_" + "4" * 32
DENY_SUBJECT_ID = "tid_" + "5" * 32
ALLOW_SUBJECT_ID = "tid_" + "6" * 32
DENY_INTENT_ID = "pin_" + "7" * 32
ALLOW_INTENT_ID = "pin_" + "8" * 32
EFFECT_ID = "document-updated"
RESOURCE_ID = "owner-document"


class _Binding(SimpleNamespace):
    def model_dump(self, *, mode: str):
        assert mode == "json"
        return {
            "requirement_id": self.requirement_id,
            "observer_id": self.observer_id,
        }


def test_legacy_permission_policy_fingerprint_remains_readable() -> None:
    entry = {
        "intent_id": DENY_INTENT_ID,
        "revision": 1,
        "intent_hash": "a" * 64,
        "binding_fingerprint": "b" * 64,
    }
    payload = {
        "project_id": PROJECT_ID,
        "policy_epoch": 3,
        "entries": [entry],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")

    snapshot = PermissionPolicySnapshot.model_validate(
        {
            "project_id": PROJECT_ID,
            "policy_epoch": 3,
            "policy_fingerprint": hashlib.sha256(encoded).hexdigest(),
            "entries": (entry,),
        },
        strict=True,
    )

    assert snapshot.entries[0].expectation is None


class _Reader:
    def __init__(self, views):
        self.views = views

    def read(self, run_id: str):
        return self.views[run_id]

    @staticmethod
    def execution_request(view):
        return view.request


class _Findings:
    def findings_for_run(self, run_id: str):
        if run_id != SOURCE_RUN_ID:
            return []
        return [
            {
                "finding": {
                    "finding_id": FINDING_ID,
                    "identity": {
                        "resource_relation": ["relation:other-role:OTHER_ROLE"]
                    },
                },
                "occurrence": {
                    "verdict": CaseVerdict.VULNERABLE.value,
                    "evidence_refs": ["ev_" + "9" * 20],
                },
            }
        ]


def _policy(*, revision: int = 1, binding_suffix: str = "a", policy_epoch: int = 4):
    entries = (
        PermissionPolicySnapshotEntry(
            intent_id=DENY_INTENT_ID,
            revision=revision,
            intent_hash="b" * 64,
            binding_fingerprint=binding_suffix * 64,
            expectation=PermissionExpectation.DENY,
            relation=PermissionIntentRelation.OTHER_ROLE,
            subject_display_name="普通成员",
            action_display_name="修改文档",
            resource_owner_display_name="项目负责人",
            protected_effects=(),
            action_candidate_id=ACTION_ID,
            subject_test_identity_id=DENY_SUBJECT_ID,
        ),
        PermissionPolicySnapshotEntry(
            intent_id=ALLOW_INTENT_ID,
            revision=1,
            intent_hash="c" * 64,
            binding_fingerprint=binding_suffix * 64,
            expectation=PermissionExpectation.ALLOW,
            relation=PermissionIntentRelation.OWNS,
            subject_display_name="项目负责人",
            action_display_name="修改文档",
            resource_owner_display_name="项目负责人",
            protected_effects=(),
            action_candidate_id=ACTION_ID,
            subject_test_identity_id=ALLOW_SUBJECT_ID,
        ),
    )
    return build_permission_policy_snapshot(PROJECT_ID, policy_epoch, entries)


def _case(subject_id: str, expectation: PermissionExpectation, suffix: str):
    return SimpleNamespace(
        case_id=f"repair-{suffix}",
        action_id=ACTION_ID,
        subject_id=subject_id,
        resource_ids=(RESOURCE_ID,),
        expectations=(expectation,),
        required_observations=("final-effect", "owner-state"),
        fingerprint=suffix * 64,
    )


def _evidence(
    case,
    twin,
    role: TwinExecutionRole,
    verdict: CaseVerdict,
    effect: ObservedEffect,
    *,
    requirements=("final-effect", "owner-state"),
):
    case = SimpleNamespace(**vars(case))
    case.required_observations = requirements
    return SimpleNamespace(
        evidence_id=("ev_" + "9" * 20 if role is TwinExecutionRole.DENY_VARIANT else "ev_" + "a" * 20),
        verdict=verdict,
        twin_role=role,
        twin_snapshot=twin,
        case_snapshot=case,
        requirement_bindings=tuple(
            _Binding(requirement_id=item, observer_id=f"observer-{index}")
            for index, item in enumerate(requirements)
        ),
        security_effect_facts=(
            SimpleNamespace(effect_id=EFFECT_ID, state=effect),
        ),
    )


def _fixture(monkeypatch):
    allow_case = _case(ALLOW_SUBJECT_ID, PermissionExpectation.ALLOW, "d")
    deny_case = _case(DENY_SUBJECT_ID, PermissionExpectation.DENY, "e")
    twin = SimpleNamespace(
        allow_case=allow_case,
        deny_case=deny_case,
        invariant=SimpleNamespace(action_id=ACTION_ID),
    )
    deny = _evidence(
        deny_case,
        twin,
        TwinExecutionRole.DENY_VARIANT,
        CaseVerdict.VULNERABLE,
        ObservedEffect.CONFIRMED,
    )
    allow = _evidence(
        allow_case,
        twin,
        TwinExecutionRole.ALLOW_CONTROL,
        CaseVerdict.SAFE,
        ObservedEffect.ABSENT,
    )
    snapshot = SimpleNamespace(
        contract=SimpleNamespace(
            actions=(SimpleNamespace(action_id=ACTION_ID, effect_ids=(EFFECT_ID,)),)
        )
    )
    source_request = SimpleNamespace(
        permission_policy=_policy(),
        project_snapshot=snapshot,
        repair_context=None,
    )
    source_view = SimpleNamespace(
        run=SimpleNamespace(run_id=SOURCE_RUN_ID, project_id=PROJECT_ID),
        publication=SimpleNamespace(
            result=SimpleNamespace(verdict=RunVerdict.BLOCK, evidence=(allow, deny))
        ),
        request=source_request,
    )
    monkeypatch.setattr(
        repair_module,
        "assess_authorization_continuity",
        lambda *_: SimpleNamespace(
            state=AuthorizationContinuityState.ORPHAN_EFFECT_CONFIRMED,
            confirmed_effects=(SimpleNamespace(effect_id=EFFECT_ID),),
        ),
    )
    monkeypatch.setattr(repair_module, "build_execution_traces", lambda *_: ())
    monkeypatch.setattr(
        repair_module,
        "locate_published_breakpoints",
        lambda *_: {
            (deny_case.case_id, ACTION_ID): SimpleNamespace(
                breakpoint_type=BreakpointType.AUTHORIZATION_BYPASS,
                precision=BreakpointPrecision.EXACT,
                amplifier_types=(BreakpointType.COMPENSATION_MASKING,),
            )
        },
    )
    reader = _Reader({SOURCE_RUN_ID: source_view})
    return RepairContractService(reader, _Findings()), reader, snapshot, twin


def test_repair_contract_is_deterministic_human_readable_and_patch_free(monkeypatch) -> None:
    service, _, _, _ = _fixture(monkeypatch)

    first = service.get(SOURCE_RUN_ID, FINDING_ID)
    second = service.get(SOURCE_RUN_ID, FINDING_ID)

    assert first == second
    assert first.reference.repair_fingerprint == first.repair_fingerprint
    assert "普通成员不得再对项目负责人的资源执行修改文档" in first.must_disappear
    assert "项目负责人仍然能够" in first.must_remain
    serialized = first.model_dump(mode="json")
    assert not ({"file", "line", "function", "patch"} & set(serialized))


def test_original_permission_change_is_rejected_before_repair_run(monkeypatch) -> None:
    service, _, _, _ = _fixture(monkeypatch)
    contract = service.get(SOURCE_RUN_ID, FINDING_ID)

    with pytest.raises(JiejianError, match="原权限要求已经改变，请按新权限重新形成检查。"):
        service.context(PROJECT_ID, contract.reference, _policy(revision=2))


def test_policy_epoch_change_is_rejected_before_repair_run(monkeypatch) -> None:
    service, _, _, _ = _fixture(monkeypatch)
    contract = service.get(SOURCE_RUN_ID, FINDING_ID)

    with pytest.raises(JiejianError, match="原权限要求已经改变，请按新权限重新形成检查。"):
        service.context(PROJECT_ID, contract.reference, _policy(policy_epoch=5))


@pytest.mark.parametrize(
    ("case", "expected", "reason"),
    (
        ("verified", RepairVerificationStatus.VERIFIED, "REPAIR_REQUIREMENTS_SATISFIED"),
        ("allow-broken", RepairVerificationStatus.NOT_VERIFIED, "ALLOW_CONTROL_BROKEN"),
        ("effect-removed", RepairVerificationStatus.NOT_VERIFIED, "PROTECTED_EFFECT_REMOVED"),
        ("evidence-lowered", RepairVerificationStatus.NOT_VERIFIED, "KEY_EVIDENCE_STANDARD_LOWERED"),
        ("evidence-strengthened", RepairVerificationStatus.VERIFIED, "REPAIR_REQUIREMENTS_SATISFIED"),
    ),
)
def test_repair_verification_requires_same_exam_allow_control_effects_and_evidence(
    monkeypatch,
    case: str,
    expected: RepairVerificationStatus,
    reason: str,
) -> None:
    service, reader, source_snapshot, twin = _fixture(monkeypatch)
    contract = service.get(SOURCE_RUN_ID, FINDING_ID)
    requirements = (
        ("owner-state",)
        if case == "evidence-lowered"
        else (
            ("final-effect", "owner-state", "supporting-extra")
            if case == "evidence-strengthened"
            else ("final-effect", "owner-state")
        )
    )
    allow = _evidence(
        twin.allow_case,
        twin,
        TwinExecutionRole.ALLOW_CONTROL,
        CaseVerdict.VULNERABLE if case == "allow-broken" else CaseVerdict.SAFE,
        ObservedEffect.ABSENT,
        requirements=requirements,
    )
    deny = _evidence(
        twin.deny_case,
        twin,
        TwinExecutionRole.DENY_VARIANT,
        CaseVerdict.SAFE,
        ObservedEffect.ABSENT,
        requirements=requirements,
    )
    snapshot = (
        SimpleNamespace(
            contract=SimpleNamespace(
                actions=(SimpleNamespace(action_id=ACTION_ID, effect_ids=()),)
            )
        )
        if case == "effect-removed"
        else source_snapshot
    )
    request = SimpleNamespace(
        permission_policy=_policy(binding_suffix="f"),
        project_snapshot=snapshot,
        repair_context=service.context(PROJECT_ID, contract.reference, _policy()),
    )
    reader.views[VERIFY_RUN_ID] = SimpleNamespace(
        run=SimpleNamespace(run_id=VERIFY_RUN_ID, project_id=PROJECT_ID),
        publication=SimpleNamespace(
            result=SimpleNamespace(verdict=RunVerdict.PASS, evidence=(allow, deny))
        ),
        request=request,
    )

    verification = service.verify_run(VERIFY_RUN_ID)

    assert verification is not None
    assert verification.status is expected
    assert verification.reason_codes == (reason,)
