# 验证长期权限意图 revision、epoch、binding、proposal 与运行快照不变量。

from __future__ import annotations

from pathlib import Path

import pytest

from product.backend.core.application_understanding import CandidateDecision
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.permission_intent import (
    IntentImplementationBindingStatus,
    PermissionIntentEffectiveState,
    PermissionIntentRelation,
    PermissionIntentRevision,
    PermissionIntentSemantic,
    permission_intent_sha256,
)
from product.backend.core.verification.permissions import PermissionExpectation
from product.backend.core.source_changes import SourceFileFingerprint, source_fingerprint
from product.backend.workflows.application_understanding.analysis.models import (
    ApplicationAnalysisResult,
)
from product.backend.workflows.permission_intents import (
    PermissionIntentActionView,
    PermissionIntentCellStatus,
    PermissionIntentCellView,
    _required_confirmation_count,
)
from tests.backend.workflows.recording.test_action_safety_setup import (
    ACTION_ID,
    PROJECT_ID,
    RECORDING_ID,
    ROLE_ID,
    _confirmation,
)
from tests.backend.workflows.security_setup.test_checks import _prepared_core


pytestmark = pytest.mark.database


def test_hash_excludes_approver_and_repeated_gui_approval_is_idempotent(
    tmp_path: Path,
) -> None:
    core = _prepared_core(tmp_path)
    try:
        before = core.permission_intents.matrix(PROJECT_ID)
        revisions_before = _revisions(core)
        source = revisions_before[0]
        semantic = PermissionIntentSemantic(
            effective_state=source.effective_state,
            subject_display_name=source.subject_display_name,
            action_display_name=source.action_display_name,
            resource_owner_display_name=source.resource_owner_display_name,
            relation=source.relation,
            expectation=source.expectation,
            protected_effects=source.protected_effects,
        )
        alternate = PermissionIntentRevision(
            **source.model_dump(mode="python", exclude={"approval"}),
            approval=source.approval.model_copy(update={"approved_by": "另一位本机用户"}),
        )
        assert source.intent_hash == alternate.intent_hash
        assert source.intent_hash == permission_intent_sha256(semantic.canonical_payload())

        repeated = core.permission_intents.confirm(
            PROJECT_ID,
            ACTION_ID,
            ROLE_ID,
            ROLE_ID,
            PermissionIntentRelation.OWNS,
            expectation=PermissionExpectation.ALLOW,
        )

        assert repeated.policy_epoch == before.policy_epoch
        assert _revisions(core) == revisions_before
    finally:
        core.close()


def test_semantic_change_and_retirement_append_history_and_advance_epoch(
    tmp_path: Path,
) -> None:
    core = _prepared_core(tmp_path)
    try:
        before = core.permission_intents.matrix(PROJECT_ID)
        changed = core.permission_intents.confirm(
            PROJECT_ID,
            ACTION_ID,
            ROLE_ID,
            ROLE_ID,
            PermissionIntentRelation.OWNS,
            expectation=PermissionExpectation.DENY,
        )
        owns = _latest_for(core, PermissionIntentRelation.OWNS)
        assert changed.policy_epoch == before.policy_epoch + 1
        assert owns.revision == 2
        assert owns.expectation is PermissionExpectation.DENY
        assert owns.effective_state is PermissionIntentEffectiveState.ACTIVE

        retired = core.permission_intents.confirm(
            PROJECT_ID,
            ACTION_ID,
            ROLE_ID,
            ROLE_ID,
            PermissionIntentRelation.OWNS,
            expectation=None,
        )
        latest = _latest(core, owns.intent_id)
        assert retired.policy_epoch == changed.policy_epoch + 1
        assert latest.intent_id == owns.intent_id
        assert latest.revision == 3
        assert latest.effective_state is PermissionIntentEffectiveState.RETIRED
        assert len(_revisions(core)) == 4
    finally:
        core.close()


def test_stale_approval_cannot_overwrite_a_newer_policy_epoch(tmp_path: Path) -> None:
    core = _prepared_core(tmp_path)
    try:
        before = core.permission_intents.matrix(PROJECT_ID)
        original_clock = core.permission_intents._clock_us
        interleaved = False

        def interleaving_clock() -> int:
            nonlocal interleaved
            if not interleaved:
                interleaved = True
                core.permission_intents._clock_us = original_clock
                core.permission_intents.confirm(
                    PROJECT_ID,
                    ACTION_ID,
                    ROLE_ID,
                    ROLE_ID,
                    PermissionIntentRelation.SAME_ROLE_OTHER_ACCOUNT,
                    expectation=PermissionExpectation.ALLOW,
                )
            return original_clock()

        core.permission_intents._clock_us = interleaving_clock
        with pytest.raises(JiejianError) as blocked:
            core.permission_intents.confirm(
                PROJECT_ID,
                ACTION_ID,
                ROLE_ID,
                ROLE_ID,
                PermissionIntentRelation.OWNS,
                expectation=PermissionExpectation.DENY,
            )

        assert blocked.value.code == ErrorCode.STATE_PRECONDITION.value
        assert core.permission_intents.matrix(PROJECT_ID).policy_epoch == before.policy_epoch + 1
        assert _latest_for(core, PermissionIntentRelation.OWNS).expectation is PermissionExpectation.ALLOW

        retried = core.permission_intents.confirm(
            PROJECT_ID,
            ACTION_ID,
            ROLE_ID,
            ROLE_ID,
            PermissionIntentRelation.OWNS,
            expectation=PermissionExpectation.DENY,
        )
        assert retried.policy_epoch == before.policy_epoch + 2
    finally:
        core.close()


def test_safety_fact_change_requires_rebind_without_advancing_epoch(
    tmp_path: Path,
) -> None:
    core = _prepared_core(tmp_path)
    try:
        before = core.permission_intents.matrix(PROJECT_ID)
        owns = _latest_for(core, PermissionIntentRelation.OWNS)
        old_binding = _binding(core, owns.intent_id, owns.revision)
        preview = core.action_safety_setup.preview(RECORDING_ID)
        command = _confirmation(preview, include_recovery=True).model_copy(
            update={"logical_name": "重新确认的测试资源"}
        )

        core.action_safety_setup.confirm(RECORDING_ID, command)

        stale = _binding(core, owns.intent_id, owns.revision)
        stale_matrix = core.permission_intents.matrix(PROJECT_ID)
        stale_cells = tuple(
            cell for action in stale_matrix.actions for cell in action.cells
        )
        assert stale.status is IntentImplementationBindingStatus.NEEDS_REVIEW
        assert stale_cells
        assert all(cell.can_confirm for cell in stale_cells)
        assert all(not cell.confirmation_blockers for cell in stale_cells)
        assert stale_matrix.required_confirmation_count == len(stale_cells)
        assert core.permission_intents.matrix(PROJECT_ID).policy_epoch == before.policy_epoch
        rebound = core.permission_intents.rebind(
            PROJECT_ID,
            owns.intent_id,
            action_candidate_id=ACTION_ID,
            subject_role_candidate_id=ROLE_ID,
            resource_owner_role_candidate_id=ROLE_ID,
        )
        assert rebound.status is IntentImplementationBindingStatus.CURRENT
        assert rebound.binding_fingerprint != old_binding.binding_fingerprint
        assert core.permission_intents.matrix(PROJECT_ID).policy_epoch == before.policy_epoch
        assert _latest_for(core, PermissionIntentRelation.OWNS) == owns
    finally:
        core.close()


def test_structural_safety_gap_blocks_human_permission_confirmation(
    tmp_path: Path,
) -> None:
    core = _prepared_core(
        tmp_path,
        confirm_permissions=False,
    )
    try:
        with core.uow_factory() as work:
            setup = work.action_safety_setups.get_for_action(PROJECT_ID, ACTION_ID)
            assert setup is not None
            work.action_safety_setups.replace(
                setup.model_copy(update={"recovery": None})
            )
            work.commit()
        matrix = core.permission_intents.matrix(PROJECT_ID)
        cells = tuple(cell for action in matrix.actions for cell in action.cells)

        assert cells
        assert all(not cell.can_confirm for cell in cells)
        assert all(cell.confirmation_blockers for cell in cells)
        assert matrix.actionable_confirmation_count == 0
        assert matrix.required_confirmation_count == 0
        with pytest.raises(JiejianError) as blocked:
            core.permission_intents.confirm(
                PROJECT_ID,
                ACTION_ID,
                ROLE_ID,
                ROLE_ID,
                PermissionIntentRelation.OWNS,
                expectation=PermissionExpectation.ALLOW,
            )
        assert blocked.value.code == ErrorCode.STATE_PRECONDITION.value
    finally:
        core.close()


def test_required_confirmation_count_keeps_optional_unselected_cells_non_blocking() -> None:
    def cell(
        relation: PermissionIntentRelation,
        expectation: PermissionExpectation | None,
        *,
        status: PermissionIntentCellStatus,
        requires_confirmation: bool,
    ) -> PermissionIntentCellView:
        return PermissionIntentCellView(
            action_candidate_id=ACTION_ID,
            subject_role_candidate_id=ROLE_ID,
            subject_role_display_name="所有者",
            resource_owner_role_candidate_id=ROLE_ID,
            resource_owner_role_display_name="所有者",
            relation=relation,
            expectation=expectation,
            status=status,
            can_confirm=True,
            requires_human_confirmation=requires_confirmation,
        )

    ready = PermissionIntentActionView(
        action_candidate_id=ACTION_ID,
        action_display_name="导出项目",
        cells=(
            cell(
                PermissionIntentRelation.OWNS,
                PermissionExpectation.ALLOW,
                status=PermissionIntentCellStatus.CURRENT,
                requires_confirmation=False,
            ),
            cell(
                PermissionIntentRelation.OTHER_ROLE,
                PermissionExpectation.DENY,
                status=PermissionIntentCellStatus.CURRENT,
                requires_confirmation=False,
            ),
            cell(
                PermissionIntentRelation.SAME_ROLE_OTHER_ACCOUNT,
                None,
                status=PermissionIntentCellStatus.UNCONFIRMED,
                requires_confirmation=True,
            ),
        ),
        gaps=(),
        required_intent_count=3,
        confirmed_intent_count=2,
        executable_intent_count=2,
        representative_gap_count=0,
        compilable=True,
    )

    assert _required_confirmation_count(ready) == 0
    needs_deny = ready.model_copy(
        update={
            "cells": (
                ready.cells[0],
                ready.cells[1].model_copy(
                    update={
                        "expectation": None,
                        "status": PermissionIntentCellStatus.UNCONFIRMED,
                        "requires_human_confirmation": True,
                    }
                ),
                ready.cells[2],
            ),
            "gaps": ("DENY_INTENT_MISSING",),
            "compilable": False,
        }
    )
    assert _required_confirmation_count(needs_deny) == 1
    assert _required_confirmation_count(
        ready.model_copy(
            update={"gaps": ("DENY_INTENT_MISSING",), "compilable": False}
        )
    ) == 0


def test_reanalysis_preserves_current_mapping_without_deleting_revision_or_epoch(
    tmp_path: Path,
) -> None:
    core = _prepared_core(tmp_path)
    try:
        current = core.application_understanding.get(PROJECT_ID)
        revisions_before = _revisions(core)
        epoch_before = core.permission_intents.matrix(PROJECT_ID).policy_epoch
        files = (
            SourceFileFingerprint(
                relative_path="app.py",
                content_sha256="e" * 64,
            ),
        )
        core.application_understanding.analyzer = _StaticAnalyzer(
            ApplicationAnalysisResult(
                source_fingerprint=source_fingerprint(files),
                files=files,
                role_candidates=current.role_candidates,
                action_candidates=current.action_candidates,
                files_read=1,
                total_bytes=1,
            )
        )

        analyzed = core.application_understanding.analyze_source(
            PROJECT_ID,
            revision=current.revision,
        )

        assert analyzed.revision == current.revision + 1
        assert _revisions(core) == revisions_before
        assert core.permission_intents.matrix(PROJECT_ID).policy_epoch == epoch_before
        owns = _latest_for(core, PermissionIntentRelation.OWNS)
        assert (
            _binding(core, owns.intent_id, owns.revision).status
            is IntentImplementationBindingStatus.CURRENT
        )
        assert len(core.permission_intents.execution_intents(PROJECT_ID)) == 2
        assert core.security_setup.compile(PROJECT_ID).project_id == PROJECT_ID
    finally:
        core.close()


def test_unresolved_binding_cannot_compile(tmp_path: Path) -> None:
    core = _prepared_core(tmp_path)
    try:
        current = core.application_understanding.get(PROJECT_ID)
        revisions_before = _revisions(core)
        epoch_before = core.permission_intents.matrix(PROJECT_ID).policy_epoch

        core.application_understanding.decide_action(
            PROJECT_ID,
            ACTION_ID,
            revision=current.revision,
            decision=CandidateDecision.REJECTED,
        )

        owns = _latest_for(core, PermissionIntentRelation.OWNS)
        assert _revisions(core) == revisions_before
        assert core.permission_intents.matrix(PROJECT_ID).policy_epoch == epoch_before
        assert (
            _binding(core, owns.intent_id, owns.revision).status
            is IntentImplementationBindingStatus.UNRESOLVED
        )
        with pytest.raises(JiejianError) as blocked:
            core.security_setup.compile(PROJECT_ID)
        assert blocked.value.code == ErrorCode.STATE_PRECONDITION.value
    finally:
        core.close()


def test_pending_proposal_does_not_change_policy_and_run_keeps_frozen_snapshot(
    tmp_path: Path,
) -> None:
    core = _prepared_core(tmp_path)
    try:
        compiled = core.security_setup.compile(PROJECT_ID)
        request = core.execution.build_request(
            compiled.profile_id,
            project_id=PROJECT_ID,
            source_fingerprint="d" * 64,
        )
        frozen = request.permission_policy
        owns = _latest_for(core, PermissionIntentRelation.OWNS)
        proposal = core.permission_intents.propose_semantic_change(
            PROJECT_ID,
            PermissionIntentSemantic(
                effective_state=PermissionIntentEffectiveState.ACTIVE,
                subject_display_name=owns.subject_display_name,
                action_display_name=owns.action_display_name,
                resource_owner_display_name=owns.resource_owner_display_name,
                relation=owns.relation,
                expectation=PermissionExpectation.DENY,
                protected_effects=owns.protected_effects,
            ),
            proposed_by="Agent",
            reason="建议收紧权限",
            intent_id=owns.intent_id,
        )
        assert proposal.status.value == "PENDING"
        assert core.permission_intents.policy_snapshot(PROJECT_ID) == frozen

        core.permission_intents.confirm(
            PROJECT_ID,
            ACTION_ID,
            ROLE_ID,
            ROLE_ID,
            PermissionIntentRelation.OWNS,
            expectation=PermissionExpectation.DENY,
        )
        live = core.permission_intents.policy_snapshot(PROJECT_ID)
        assert live.policy_epoch == frozen.policy_epoch + 1
        assert live.policy_fingerprint != frozen.policy_fingerprint
        assert request.permission_policy == frozen
    finally:
        core.close()


class _StaticAnalyzer:
    def __init__(self, result: ApplicationAnalysisResult) -> None:
        self._result = result

    def analyze(self, _project_id: str, _source_root: str) -> ApplicationAnalysisResult:
        return self._result


def _revisions(core) -> tuple[PermissionIntentRevision, ...]:
    with core.uow_factory() as work:
        return work.permission_intents.list_revisions(PROJECT_ID)


def _latest_for(core, relation: PermissionIntentRelation) -> PermissionIntentRevision:
    return next(item for item in core.permission_intents.current_intents(PROJECT_ID) if item.relation is relation)


def _latest(core, intent_id: str) -> PermissionIntentRevision:
    with core.uow_factory() as work:
        revision = work.permission_intents.latest(intent_id)
    assert revision is not None
    return revision


def _binding(core, intent_id: str, revision: int):
    with core.uow_factory() as work:
        binding = work.permission_intents.binding(intent_id, revision)
    assert binding is not None
    return binding
