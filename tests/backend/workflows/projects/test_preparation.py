# 验证测试准备服务只重算现有事实，并幂等执行两个安全机械动作。

from __future__ import annotations

from types import SimpleNamespace

import pytest

from product.backend.core.application_understanding import CandidateDecision
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.permission_intent import PermissionIntentRelation
from product.backend.core.verification.permissions import PermissionExpectation
from product.backend.workflows.permission_intents import (
    PermissionIntentActionView,
    PermissionIntentCellStatus,
    PermissionIntentCellView,
    PermissionIntentMatrixView,
)
from product.backend.workflows.projects.preparation import (
    PreparationAutoAction,
    PreparationItemKind,
    PreparationItemStatus,
    ProjectPreparationService,
)
from product.backend.workflows.recording.safety_setup import (
    ActionSafetyAssetInspection,
    ActionSafetyAssetKind,
    ActionSafetyAssetStatus,
    ActionSafetySetupInspection,
)
from product.backend.workflows.source_changes import SourceRevalidationInspectionStatus
from product.backend.workflows.test_identities import (
    TestIdentityStatus as IdentityStatus,
    TestIdentityView as IdentityView,
)
from tests.backend.workflows.security_setup.test_checks import (
    PEER_IDENTITY_ID,
    _prepared_core,
)
from tests.backend.workflows.recording.test_action_safety_setup import (
    ACTION_ID,
    IDENTITY_ID,
    PROJECT_ID,
    RECORDING_ID,
    ROLE_ID,
)


pytestmark = pytest.mark.database

OTHER_ROLE_ID = "role_" + "8" * 32
OTHER_IDENTITY_ID = "tid_" + "9" * 32


def test_prepare_safe_builds_only_missing_profile_and_then_becomes_zero_write(
    tmp_path,
) -> None:
    core = _prepared_core(tmp_path)
    try:
        before = core.project_preparation.status(PROJECT_ID)
        assert before.external_blockers == ()
        assert before.auto_action_count == 1
        assert before.items[-1].kind is PreparationItemKind.PROFILE
        assert before.items[-1].auto_action is PreparationAutoAction.BUILD_CURRENT_PROFILE

        prepared = core.project_preparation.prepare_safe(PROJECT_ID)

        assert prepared.ready is True
        with core.uow_factory() as work:
            profile_count = len(work.execution_profiles.list_for_project(PROJECT_ID))
            identity_count = len(work.test_identities.list_for_project(PROJECT_ID))

        repeated = core.project_preparation.prepare_safe(PROJECT_ID)
        with core.uow_factory() as work:
            assert len(work.execution_profiles.list_for_project(PROJECT_ID)) == profile_count
            assert len(work.test_identities.list_for_project(PROJECT_ID)) == identity_count
        assert repeated.ready is True
    finally:
        core.close()


def test_missing_identity_record_is_created_once_and_still_requires_login(tmp_path) -> None:
    core = _prepared_core(tmp_path)
    try:
        core.test_identities.delete(PEER_IDENTITY_ID)

        before = core.project_preparation.status(PROJECT_ID)
        identity_auto = tuple(
            item
            for item in before.items
            if item.auto_action is PreparationAutoAction.ENSURE_IDENTITY_RECORD
        )
        assert len(identity_auto) == 1
        assert identity_auto[0].status is PreparationItemStatus.AUTO

        after = core.project_preparation.prepare_safe(PROJECT_ID)
        identities = core.test_identities.list(PROJECT_ID)

        assert len(identities) == 2
        created = next(item for item in identities if item.identity_id != IDENTITY_ID)
        assert created.status is IdentityStatus.NOT_PREPARED
        assert any(
            item.identity_id == created.identity_id
            and item.status is PreparationItemStatus.USER
            for item in after.items
        )

        core.project_preparation.prepare_safe(PROJECT_ID)
        assert len(core.test_identities.list(PROJECT_ID)) == 2
    finally:
        core.close()


def test_existing_unprepared_identity_is_user_work_not_a_new_record(tmp_path) -> None:
    core = _prepared_core(tmp_path)
    try:
        core.test_identities.reset(PEER_IDENTITY_ID)
        before_count = len(core.test_identities.list(PROJECT_ID))

        view = core.project_preparation.prepare_safe(PROJECT_ID)

        assert len(core.test_identities.list(PROJECT_ID)) == before_count
        assert any(
            item.identity_id == PEER_IDENTITY_ID
            and item.status is PreparationItemStatus.USER
            and item.auto_action is None
            for item in view.items
        )
    finally:
        core.close()


def test_missing_flow_is_user_work_and_never_generates_recording() -> None:
    harness = _Harness(recording=False)

    view = harness.service.prepare_safe(PROJECT_ID)

    assert _kind(view, PreparationItemKind.FLOW).status is PreparationItemStatus.USER
    assert _kind(view, PreparationItemKind.RESOURCE).status is PreparationItemStatus.BLOCKED
    assert harness.safety.confirm_count == 0


def test_first_recording_without_identity_or_intent_goes_to_identities() -> None:
    harness = _Harness(
        recording=False,
        identity_status=None,
        intent_present=False,
    )

    view = harness.service.status(PROJECT_ID)

    assert view.next_path == "/identities"
    assert view.next_item_key == "identity:recording-bootstrap"
    assert {item.category for item in view.external_blockers} == set()
    assert harness.permission_intents._matrix.required_confirmation_count == 0


def test_prepared_identity_without_flow_or_intent_goes_to_flows() -> None:
    harness = _Harness(recording=False, intent_present=False)

    view = harness.service.status(PROJECT_ID)

    assert view.next_path == "/flows"
    assert {item.category for item in view.external_blockers} == set()


def test_actionable_unconfirmed_permission_becomes_the_next_step() -> None:
    harness = _Harness(assets_current=True, intent_present=False)

    view = harness.service.status(PROJECT_ID)

    assert harness.permission_intents._matrix.required_confirmation_count == 1
    assert {item.category for item in view.external_blockers} == {"PERMISSION"}
    assert view.next_path == "/permissions"


@pytest.mark.parametrize("candidate_count", [1, 2])
def test_finite_safety_candidates_stay_user_and_are_never_confirmed(
    candidate_count: int,
) -> None:
    harness = _Harness(candidate_count=candidate_count)

    view = harness.service.prepare_safe(PROJECT_ID)

    for kind in (
        PreparationItemKind.RESOURCE,
        PreparationItemKind.OBSERVATION,
        PreparationItemKind.RECOVERY,
        PreparationItemKind.EFFECT,
    ):
        assert _kind(view, kind).status is PreparationItemStatus.USER
    assert harness.safety.confirm_count == 0
    assert harness.checks.prepare_count == 0


def test_missing_observation_and_recovery_candidates_fail_closed() -> None:
    harness = _Harness(candidate_count=0)

    view = harness.service.status(PROJECT_ID)

    assert _kind(view, PreparationItemKind.OBSERVATION).status is PreparationItemStatus.BLOCKED
    assert _kind(view, PreparationItemKind.RECOVERY).status is PreparationItemStatus.BLOCKED
    assert _kind(view, PreparationItemKind.EFFECT).status is PreparationItemStatus.BLOCKED
    assert view.blocked_count >= 3


def test_unprepared_identity_does_not_invalidate_current_action_assets() -> None:
    harness = _Harness(
        identity_status=IdentityStatus.NOT_PREPARED,
        assets_current=True,
    )

    view = harness.service.status(PROJECT_ID)

    assert _kind(view, PreparationItemKind.IDENTITY).status is PreparationItemStatus.USER
    for kind in (
        PreparationItemKind.FLOW,
        PreparationItemKind.RESOURCE,
        PreparationItemKind.OBSERVATION,
        PreparationItemKind.RECOVERY,
        PreparationItemKind.EFFECT,
    ):
        assert _kind(view, kind).status is PreparationItemStatus.READY
    assert view.next_path == "/identities"


def test_profile_is_the_only_auto_step_after_all_business_prerequisites() -> None:
    harness = _Harness(assets_current=True)

    view = harness.service.status(PROJECT_ID)

    profile = _kind(view, PreparationItemKind.PROFILE)
    assert profile.status is PreparationItemStatus.AUTO
    assert profile.auto_action is PreparationAutoAction.BUILD_CURRENT_PROFILE
    assert view.next_path == "/preparation"
    assert view.next_label == "自动完成这一步"


def test_fully_ready_preparation_routes_to_validation_and_status_is_zero_write() -> None:
    harness = _Harness(assets_current=True, profile_current=True)

    first = harness.service.status(PROJECT_ID)
    second = harness.service.status(PROJECT_ID)

    assert first == second
    assert second.ready is True
    assert second.next_path == "/validation"
    assert second.next_label == "前往验证运行"
    assert harness.identities.create_count == 0
    assert harness.checks.prepare_count == 0
    assert harness.safety.confirm_count == 0


def test_safe_automation_whitelist_has_exactly_two_actions() -> None:
    assert set(PreparationAutoAction) == {
        PreparationAutoAction.ENSURE_IDENTITY_RECORD,
        PreparationAutoAction.BUILD_CURRENT_PROFILE,
    }


def test_permission_and_source_change_blockers_prevent_every_write() -> None:
    permission = _Harness(permission_blocked=True, assets_current=True)
    source_change = _Harness(source_change_blocked=True)

    permission_view = permission.service.prepare_safe(PROJECT_ID)
    source_view = source_change.service.prepare_safe(PROJECT_ID)

    assert {item.category for item in permission_view.external_blockers} == {"PERMISSION"}
    assert {item.category for item in source_view.external_blockers} == {"SOURCE_CHANGE"}
    assert permission_view.next_item_key == permission_view.external_blockers[0].key
    assert source_view.next_item_key == source_view.external_blockers[0].key
    assert permission.identities.create_count == source_change.identities.create_count == 0
    assert permission.checks.prepare_count == source_change.checks.prepare_count == 0
    assert permission.safety.confirm_count == source_change.safety.confirm_count == 0


def test_unselected_matrix_cells_do_not_block_confirmed_permission_scope() -> None:
    # CheckPreview 的聚合缺口包含未选择的矩阵单元，不得覆盖 Matrix 对正式权限考题的判断。
    preview = SimpleNamespace(
        gaps=(
            SimpleNamespace(
                code="PERMISSION_INTENT_UNCONFIRMED",
                next_path="/permissions",
            ),
        )
    )

    assert ProjectPreparationService._preview_external_blockers(preview) == []


def _kind(view, kind: PreparationItemKind):
    return next(item for item in view.items if item.kind is kind)


def _identity(*, status: IdentityStatus = IdentityStatus.PREPARED) -> IdentityView:
    return IdentityView(
        identity_id=OTHER_IDENTITY_ID,
        project_id=PROJECT_ID,
        role_candidate_id=OTHER_ROLE_ID,
        role_canonical_key="member",
        role_display_name="普通成员",
        label="Bob 测试账号",
        confirmed_endpoint="http://127.0.0.1:18080",
        auth_method=None,
        status=status,
        review_reasons=(),
        cookie_count=0,
        prepared_at_us=1 if status is IdentityStatus.PREPARED else None,
        refreshed_at_us=1 if status is IdentityStatus.PREPARED else None,
        created_at_us=1,
        updated_at_us=1,
    )


def _matrix(
    *,
    permission_blocked: bool,
    intent_present: bool,
    assets_current: bool,
) -> PermissionIntentMatrixView:
    status = (
        PermissionIntentCellStatus.UNCONFIRMED
        if not intent_present
        else PermissionIntentCellStatus.NEEDS_REVIEW
        if permission_blocked
        else PermissionIntentCellStatus.CURRENT
    )
    can_confirm = assets_current
    requires_confirmation = can_confirm and (
        not intent_present or permission_blocked
    )
    confirmation_blockers = () if can_confirm else ("ACTION_SAFETY_SETUP_STALE",)
    cell = PermissionIntentCellView(
        action_candidate_id=ACTION_ID,
        subject_role_candidate_id=OTHER_ROLE_ID,
        subject_role_display_name="普通成员",
        resource_owner_role_candidate_id=ROLE_ID,
        resource_owner_role_display_name="所有者",
        relation=PermissionIntentRelation.OTHER_ROLE,
        expectation=PermissionExpectation.DENY if intent_present else None,
        status=status,
        review_reasons=(
            ("PERMISSION_INTENT_UNCONFIRMED",)
            if not intent_present
            else ("ACTION_SAFETY_SETUP_CHANGED",)
            if permission_blocked
            else ()
        ),
        intent_id="intent_" + "1" * 32 if intent_present else None,
        intent_revision=1 if intent_present else None,
        intent_hash="1" * 64 if intent_present else None,
        policy_epoch=1 if intent_present else None,
        binding_fingerprint="2" * 64 if intent_present else None,
        representative_test_identity_id=(
            None if permission_blocked else OTHER_IDENTITY_ID
        ),
        can_confirm=can_confirm,
        requires_human_confirmation=requires_confirmation,
        confirmation_blockers=confirmation_blockers,
    )
    action = PermissionIntentActionView(
        action_candidate_id=ACTION_ID,
        action_display_name="导出完整项目",
        resource_logical_name="完整项目包",
        cells=(cell,),
        gaps=("ACTION_SAFETY_SETUP_CHANGED",) if not assets_current else (),
        required_intent_count=1 if intent_present else 0,
        confirmed_intent_count=1 if intent_present else 0,
        executable_intent_count=(
            1 if intent_present and not permission_blocked and assets_current else 0
        ),
        representative_gap_count=0,
        compilable=intent_present and not permission_blocked and assets_current,
    )
    return PermissionIntentMatrixView(
        project_id=PROJECT_ID,
        policy_epoch=1,
        actions=(action,),
        confirmed_count=1 if intent_present else 0,
        review_required_count=1 if permission_blocked else 0,
        unconfirmed_count=0 if intent_present else 1,
        executable_count=(
            1 if intent_present and not permission_blocked and assets_current else 0
        ),
        representative_gap_count=0,
        compilable_action_count=(
            1 if intent_present and not permission_blocked and assets_current else 0
        ),
        actionable_confirmation_count=1 if can_confirm else 0,
        required_confirmation_count=1 if requires_confirmation else 0,
    )


class _Repo:
    def __init__(self, records=()):
        self.records = list(records)

    def get(self, record_id):
        return next(
            (
                item
                for item in self.records
                if getattr(item, "project_id", None) == record_id
                or getattr(item, "recording_id", None) == record_id
            ),
            None,
        )

    def list_for_project(self, project_id):
        return tuple(
            item for item in self.records if getattr(item, "project_id", None) == project_id
        )


class _Work:
    def __init__(self):
        self.projects = _Repo((SimpleNamespace(project_id=PROJECT_ID),))
        role = SimpleNamespace(
            candidate_id=OTHER_ROLE_ID,
            decision=CandidateDecision.CONFIRMED,
            stale=False,
        )
        owner = SimpleNamespace(
            candidate_id=ROLE_ID,
            decision=CandidateDecision.CONFIRMED,
            stale=False,
        )
        action = SimpleNamespace(
            candidate_id=ACTION_ID,
            decision=CandidateDecision.CONFIRMED,
            stale=False,
        )
        understanding = SimpleNamespace(
            project_id=PROJECT_ID,
            confirmed_endpoint="http://127.0.0.1:18080",
            endpoint_source_fingerprint="a" * 64,
            endpoint_reachable=True,
            source_analysis_authorized=True,
            source_fingerprint="b" * 64,
            role_candidates=(role, owner),
            action_candidates=(action,),
        )
        self.application_understanding = _Repo((understanding,))
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class _Identities:
    def __init__(self, *, status: IdentityStatus | None):
        self.records = [] if status is None else [_identity(status=status)]
        self.create_count = 0

    def list(self, project_id):
        assert project_id == PROJECT_ID
        return tuple(self.records)

    def create(self, project_id, *, role_candidate_id, label):
        self.create_count += 1
        created = _identity(status=IdentityStatus.NOT_PREPARED).model_copy(
            update={"identity_id": "tid_" + "6" * 32, "label": label}
        )
        self.records.append(created)
        return created


class _PermissionIntents:
    def __init__(
        self,
        *,
        blocked: bool,
        intent_present: bool,
        assets_current: bool,
    ):
        self._matrix = _matrix(
            permission_blocked=blocked,
            intent_present=intent_present,
            assets_current=assets_current,
        )

    def matrix(self, project_id):
        assert project_id == PROJECT_ID
        return self._matrix


class _Safety:
    def __init__(
        self,
        *,
        recording: bool,
        candidate_count: int,
        assets_current: bool,
    ):
        recording_id = RECORDING_ID if recording else None
        if not recording:
            assets = tuple(
                ActionSafetyAssetInspection(
                    kind=kind,
                    status=(
                        ActionSafetyAssetStatus.MISSING
                        if kind is ActionSafetyAssetKind.FLOW
                        else ActionSafetyAssetStatus.MISSING
                    ),
                    reason_codes=(
                        "COMPLETED_FLOW_MISSING"
                        if kind is ActionSafetyAssetKind.FLOW
                        else "UPSTREAM_FLOW_NOT_CURRENT"
                    ,),
                    candidate_count=0,
                )
                for kind in ActionSafetyAssetKind
            )
        else:
            assets = tuple(
                ActionSafetyAssetInspection(
                    kind=kind,
                    status=(
                        ActionSafetyAssetStatus.CURRENT
                        if assets_current or kind is ActionSafetyAssetKind.FLOW
                        else ActionSafetyAssetStatus.MISSING
                    ),
                    reason_codes=(
                        ()
                        if assets_current or kind is ActionSafetyAssetKind.FLOW
                        else (f"{kind.value}_UNCONFIRMED",)
                    ),
                    candidate_count=(
                        1
                        if kind in {
                            ActionSafetyAssetKind.FLOW,
                            ActionSafetyAssetKind.RESOURCE,
                        }
                        else candidate_count
                    ),
                    recording_id=recording_id,
                )
                for kind in ActionSafetyAssetKind
            )
        self._inspection = ActionSafetySetupInspection(
            project_id=PROJECT_ID,
            action_candidate_id=ACTION_ID,
            action_display_name="导出完整项目",
            recording_id=recording_id,
            state_changing=True,
            assets=assets,
            fully_current=assets_current,
        )
        self.confirm_count = 0

    def inspect_action(self, project_id, action_candidate_id):
        assert project_id == PROJECT_ID
        assert action_candidate_id == ACTION_ID
        return self._inspection

    def preview(self, *args, **kwargs):
        raise AssertionError("Preparation must consume inspect_action, not preview")

    def confirm(self, *args, **kwargs):
        self.confirm_count += 1
        raise AssertionError("prepare_safe must not confirm safety candidates")


class _Checks:
    def __init__(self, *, profile_current: bool):
        self.prepare_count = 0
        self._profile_current = profile_current

    def preview(self, project_id):
        return SimpleNamespace(
            gaps=() if self._profile_current else (
                SimpleNamespace(
                    code="GENERATED_PROFILE_MISSING",
                    next_path="/validation",
                ),
            )
        )

    def prepare(self, project_id):
        self.prepare_count += 1
        return self.preview(project_id)


class _SourceChanges:
    def __init__(self, *, blocked: bool):
        self._blocked = blocked

    def latest(self, project_id):
        if not self._blocked:
            return None
        return (
            SimpleNamespace(change_id="chg_" + "1" * 32),
            object(),
            object(),
        )

    def inspect_revalidation(self, project_id, change_id):
        assert self._blocked
        assert change_id == "chg_" + "1" * 32
        return SimpleNamespace(
            status=SourceRevalidationInspectionStatus.NO_BASELINE,
            reason_codes=("NO_BASELINE",),
        )


class _Harness:
    def __init__(
        self,
        *,
        recording: bool = True,
        candidate_count: int = 1,
        permission_blocked: bool = False,
        source_change_blocked: bool = False,
        identity_status: IdentityStatus | None = IdentityStatus.PREPARED,
        assets_current: bool = False,
        intent_present: bool = True,
        profile_current: bool = False,
    ) -> None:
        self.work = _Work()
        self.identities = _Identities(status=identity_status)
        self.safety = _Safety(
            recording=recording,
            candidate_count=candidate_count,
            assets_current=assets_current,
        )
        self.checks = _Checks(profile_current=profile_current)
        self.permission_intents = _PermissionIntents(
            blocked=permission_blocked,
            intent_present=intent_present,
            assets_current=assets_current,
        )
        self.service = ProjectPreparationService(
            lambda: self.work,
            test_identities=self.identities,
            permission_intents=self.permission_intents,
            action_safety_setup=self.safety,
            checks=self.checks,
            source_changes=_SourceChanges(blocked=source_change_blocked),
        )
