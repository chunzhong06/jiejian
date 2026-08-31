# 验证录制候选的确定性归一、顺序和确认前安全缺口。

from __future__ import annotations

import hashlib
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace

import pytest

from product.backend.core.application_understanding import (
    ActionCandidate,
    ActionRiskHint,
    ApplicationUnderstanding,
    CandidateConfidence,
    CandidateDecision,
    CandidateOrigin,
    RoleCandidate,
)
from product.backend.core.lifecycle import JobState, ProjectStatus
from product.backend.core.recording import Recording, RecordingState, RecordingStateEvent
from product.backend.core.test_setup import RecoveryBindingKind
from product.backend.core.test_identity import (
    TestIdentity as Identity,
    TestIdentityAuthMethod as IdentityAuthMethod,
)
from product.backend.infra.storage import (
    FlowDraftRevisionRecord,
    JobRecord,
    ProjectRecord,
    RecordingRecord,
)
from product.backend.composition import ApplicationCore
from product.backend.workflows.recording.lifecycle import RecordingLifecycle
from product.backend.workflows.recording.processing import FlowDraftProcessor
from product.backend.workflows.recording.review import FlowDraftReviewer
from product.backend.workflows.recording.safety_setup import (
    ActionSafetyAssetKind,
    ActionSafetyAssetStatus,
    ActionSafetySetupService,
    ConfirmActionSafetySetup,
)
from product.backend.core.verification.permissions import SecurityEffectKind
from product.protocols import (
    ConfirmFlowDraftResource,
    ConfirmFlowDraftTarget,
    RecordingAuthMethod,
    RecordingBudget,
    RecordingEvent,
    RecordingEventKind,
    RecordingRunnerRequest,
    RecordingSessionRef,
    canonical_flow_draft_json_bytes,
)
from product.protocols.web.target import WebTargetScope

pytestmark = pytest.mark.database

PROJECT_ID = "safety-project"
RECORDING_ID = "rec_" + "1" * 32
JOB_ID = "job_" + "2" * 32
IDENTITY_ID = "tid_" + "3" * 32
ROLE_ID = "role_" + "4" * 32
ACTION_ID = "action_" + "5" * 32
SOURCE_FINGERPRINT = "a" * 64
ENDPOINT_FINGERPRINT = "b" * 64
NOW_US = 1_830_000_000_000_000


class _FakeSecretStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.read_count = 0

    def configured(self, secret_ref: str) -> bool:
        return secret_ref in self.values

    def read(self, secret_ref: str) -> str:
        self.read_count += 1
        return self.values[secret_ref]

    def write(self, secret_ref: str, value: str) -> None:
        self.values[secret_ref] = value

    def delete(self, secret_ref: str) -> None:
        self.values.pop(secret_ref, None)


def test_candidates_are_deterministic_before_confirmation(
    tmp_path: Path,
) -> None:
    store = _FakeSecretStore()
    secret_ref = f"cred:jiejian/test-identity/{PROJECT_ID}/{IDENTITY_ID}/bearer"
    store.write(secret_ref, "opaque-test-state")
    core = ApplicationCore(
        tmp_path / "var",
        secret_store=store,
        clock_us=lambda: NOW_US + 100,
    )
    try:
        _persist_completed_recording(core, secret_ref)
        preview = core.action_safety_setup.preview(RECORDING_ID)

        assert preview.state_changing is True
        assert len(preview.resource_candidates) == 1
        assert len(preview.observation_candidates) == 1
        assert len(preview.recovery_candidates) == 1
        assert len(preview.security_effect_candidates) == 1
        assert set(preview.gaps) == {
            "TEST_RESOURCE_UNCONFIRMED",
            "OBSERVATION_UNCONFIRMED",
            "RECOVERY_UNCONFIRMED",
            "SECURITY_EFFECT_UNCONFIRMED",
        }
        assert preview.automatic_execution_allowed is False
        assert preview.resource_candidates[0].candidate_id.startswith("trc_")
        assert preview.observation_candidates[0].label == "独立读取并核对业务结果"
        assert preview.observation_candidates[0].source_recording_id == RECORDING_ID
        assert preview.recovery_candidates[0].candidate_id.startswith("rcc_")
    finally:
        core.close()


def test_read_action_uses_target_response_for_disclosure_proof_setup(
    tmp_path: Path,
) -> None:
    store = _FakeSecretStore()
    secret_ref = f"cred:jiejian/test-identity/{PROJECT_ID}/{IDENTITY_ID}/bearer"
    store.write(secret_ref, "opaque-test-state")
    core = ApplicationCore(
        tmp_path / "var",
        secret_store=store,
        clock_us=lambda: NOW_US + 100,
    )
    try:
        _persist_completed_recording(core, secret_ref, read_action=True)
        preview = core.action_safety_setup.preview(RECORDING_ID)

        assert preview.state_changing is False
        assert len(preview.observation_candidates) == 1
        assert preview.observation_candidates[0].source_recording_id == RECORDING_ID
        assert preview.observation_candidates[0].method == "GET"
        assert preview.recovery_candidates == ()
        assert len(preview.security_effect_candidates) == 1
        effect = preview.security_effect_candidates[0]
        assert effect.kind is SecurityEffectKind.DATA_DISCLOSURE
        assert effect.protected_fields == ("materials", "project_id")

        confirmed = core.action_safety_setup.confirm(
            RECORDING_ID,
            ConfirmActionSafetySetup(
                logical_name="日常协作资料",
                resource_type="项目",
            ),
        )
        assert confirmed.ready is True
        assert confirmed.recovery_status == "NOT_REQUIRED"
        assert confirmed.confirmed_setup is not None
        assert confirmed.confirmed_setup.effect is not None
        assert confirmed.confirmed_setup.effect.kind is SecurityEffectKind.DATA_DISCLOSURE
    finally:
        core.close()


def test_action_inspection_projects_five_current_assets_without_writes(
    tmp_path: Path,
) -> None:
    store, core, _secret_ref = _confirmed_core(tmp_path)
    try:
        with core.uow_factory() as work:
            before = work.action_safety_setups.get_for_action(PROJECT_ID, ACTION_ID)

        first = core.action_safety_setup.inspect_action(PROJECT_ID, ACTION_ID)
        second = core.action_safety_setup.inspect_action(PROJECT_ID, ACTION_ID)

        assert tuple(item.kind for item in first.assets) == tuple(ActionSafetyAssetKind)
        assert all(
            item.status is ActionSafetyAssetStatus.CURRENT for item in first.assets
        )
        assert first.fully_current is True
        assert second == first
        assert store.read_count == 0
        with core.uow_factory() as work:
            assert work.action_safety_setups.get_for_action(PROJECT_ID, ACTION_ID) == before
    finally:
        core.close()


def test_action_inspection_reports_missing_flow_without_a_completed_target(
    tmp_path: Path,
) -> None:
    core = ApplicationCore(tmp_path / "var", secret_store=_FakeSecretStore())
    try:
        with core.uow_factory() as work:
            work.projects.add(
                ProjectRecord(
                    project_id=PROJECT_ID,
                    name="安全准备测试",
                    status=ProjectStatus.DRAFT,
                    created_at_us=NOW_US,
                    updated_at_us=NOW_US,
                )
            )
            work.application_understanding.add(_understanding())
            work.commit()

        inspection = core.action_safety_setup.inspect_action(PROJECT_ID, ACTION_ID)

        assert _asset(inspection, ActionSafetyAssetKind.FLOW).status is ActionSafetyAssetStatus.MISSING
        assert _asset(inspection, ActionSafetyAssetKind.FLOW).reason_codes == (
            "COMPLETED_FLOW_MISSING",
        )
        assert all(
            item.status is not ActionSafetyAssetStatus.CURRENT
            for item in inspection.assets[1:]
        )
    finally:
        core.close()


def test_stale_resource_hash_invalidates_only_resource_and_its_dependents(
    tmp_path: Path,
) -> None:
    _store, core, _secret_ref = _confirmed_core(tmp_path)
    try:
        _replace_setup(
            core,
            lambda setup: setup.model_copy(
                update={
                    "resource": setup.resource.model_copy(
                        update={"flow_sha256": "f" * 64}
                    )
                }
            ),
        )

        inspection = core.action_safety_setup.inspect_action(PROJECT_ID, ACTION_ID)

        assert _asset(inspection, ActionSafetyAssetKind.FLOW).status is ActionSafetyAssetStatus.CURRENT
        assert _asset(inspection, ActionSafetyAssetKind.RESOURCE).status is ActionSafetyAssetStatus.STALE
        for kind in (
            ActionSafetyAssetKind.OBSERVATION,
            ActionSafetyAssetKind.RECOVERY,
            ActionSafetyAssetKind.EFFECT,
        ):
            assert _asset(inspection, kind).status is ActionSafetyAssetStatus.STALE
            assert _asset(inspection, kind).reason_codes == (
                "UPSTREAM_RESOURCE_NOT_CURRENT",
            )
    finally:
        core.close()


def test_observation_source_change_does_not_spread_to_unrelated_assets(
    tmp_path: Path,
) -> None:
    _store, core, _secret_ref = _confirmed_core(tmp_path)
    try:
        _replace_setup(
            core,
            lambda setup: setup.model_copy(
                update={
                    "observation": setup.observation.model_copy(
                        update={"source_step_id": "obsolete-step"}
                    )
                }
            ),
        )

        inspection = core.action_safety_setup.inspect_action(PROJECT_ID, ACTION_ID)

        assert _asset(inspection, ActionSafetyAssetKind.OBSERVATION).status is ActionSafetyAssetStatus.STALE
        for kind in (
            ActionSafetyAssetKind.FLOW,
            ActionSafetyAssetKind.RESOURCE,
            ActionSafetyAssetKind.RECOVERY,
            ActionSafetyAssetKind.EFFECT,
        ):
            assert _asset(inspection, kind).status is ActionSafetyAssetStatus.CURRENT
    finally:
        core.close()


def test_recovery_candidate_and_not_required_semantics_are_current_only_when_exact(
    tmp_path: Path,
) -> None:
    _store, core, _secret_ref = _confirmed_core(tmp_path)
    try:
        _replace_setup(
            core,
            lambda setup: setup.model_copy(
                update={
                    "recovery": setup.recovery.model_copy(
                        update={"source_step_id": "obsolete-step"}
                    )
                }
            ),
        )
        stale_candidate = core.action_safety_setup.inspect_action(PROJECT_ID, ACTION_ID)
        assert _asset(stale_candidate, ActionSafetyAssetKind.RECOVERY).status is ActionSafetyAssetStatus.STALE

        _replace_setup(
            core,
            lambda setup: setup.model_copy(
                update={
                    "recovery": setup.recovery.model_copy(
                        update={
                            "kind": RecoveryBindingKind.NOT_REQUIRED,
                            "source_step_id": None,
                            "method": None,
                            "path_template": None,
                            "json_body_template": {},
                        }
                    )
                }
            ),
        )
        stale_not_required = core.action_safety_setup.inspect_action(
            PROJECT_ID,
            ACTION_ID,
        )
        assert _asset(stale_not_required, ActionSafetyAssetKind.RECOVERY).status is ActionSafetyAssetStatus.STALE
    finally:
        core.close()


def test_not_required_recovery_is_current_for_a_read_action(tmp_path: Path) -> None:
    store = _FakeSecretStore()
    secret_ref = f"cred:jiejian/test-identity/{PROJECT_ID}/{IDENTITY_ID}/bearer"
    store.write(secret_ref, "opaque-test-state")
    core = ApplicationCore(tmp_path / "var", secret_store=store)
    try:
        _persist_completed_recording(core, secret_ref, read_action=True)
        core.action_safety_setup.confirm(
            RECORDING_ID,
            ConfirmActionSafetySetup(
                logical_name="日常协作资料",
                resource_type="项目",
            ),
        )

        inspection = core.action_safety_setup.inspect_action(PROJECT_ID, ACTION_ID)

        assert inspection.state_changing is False
        assert _asset(inspection, ActionSafetyAssetKind.RECOVERY).status is ActionSafetyAssetStatus.CURRENT
    finally:
        core.close()


def test_effect_semantic_change_only_invalidates_effect(tmp_path: Path) -> None:
    _store, core, _secret_ref = _confirmed_core(tmp_path)
    try:
        _replace_setup(
            core,
            lambda setup: setup.model_copy(
                update={
                    "effect": setup.effect.model_copy(
                        update={"kind": SecurityEffectKind.OBJECT_CREATION}
                    )
                }
            ),
        )

        inspection = core.action_safety_setup.inspect_action(PROJECT_ID, ACTION_ID)

        assert _asset(inspection, ActionSafetyAssetKind.EFFECT).status is ActionSafetyAssetStatus.STALE
        for kind in (
            ActionSafetyAssetKind.FLOW,
            ActionSafetyAssetKind.RESOURCE,
            ActionSafetyAssetKind.OBSERVATION,
            ActionSafetyAssetKind.RECOVERY,
        ):
            assert _asset(inspection, kind).status is ActionSafetyAssetStatus.CURRENT
    finally:
        core.close()


def test_login_and_secret_availability_do_not_change_static_asset_currentness(
    tmp_path: Path,
) -> None:
    store, core, secret_ref = _confirmed_core(tmp_path)
    try:
        store.delete(secret_ref)
        unavailable = core.action_safety_setup.inspect_action(PROJECT_ID, ACTION_ID)
        assert all(
            item.status is ActionSafetyAssetStatus.CURRENT
            for item in unavailable.assets
        )
        assert store.read_count == 0

        with core.uow_factory() as work:
            identity = work.test_identities.get(IDENTITY_ID)
            assert identity is not None
            work.test_identities.replace(
                identity.model_copy(
                    update={
                        "auth_method": None,
                        "bearer_secret_ref": None,
                        "prepared_at_us": None,
                        "refreshed_at_us": None,
                    }
                )
            )
            work.commit()
        unprepared = core.action_safety_setup.inspect_action(PROJECT_ID, ACTION_ID)
        assert all(
            item.status is ActionSafetyAssetStatus.CURRENT
            for item in unprepared.assets
        )
    finally:
        core.close()


def test_recording_selection_prefers_confirmed_setup_then_latest_target() -> None:
    older = SimpleNamespace(recording_id="rec-old", updated_at_us=1)
    newer = SimpleNamespace(recording_id="rec-new", updated_at_us=2)
    setup = SimpleNamespace(resource=SimpleNamespace(recording_id="rec-old"))

    assert ActionSafetySetupService._recording_for_action((older, newer), setup) is older
    assert ActionSafetySetupService._recording_for_action((older, newer), None) is newer


def _confirmed_core(tmp_path: Path):
    store = _FakeSecretStore()
    secret_ref = f"cred:jiejian/test-identity/{PROJECT_ID}/{IDENTITY_ID}/bearer"
    store.write(secret_ref, "opaque-test-state")
    core = ApplicationCore(tmp_path / "var", secret_store=store)
    _persist_completed_recording(core, secret_ref)
    core.action_safety_setup.confirm(
        RECORDING_ID,
        ConfirmActionSafetySetup(
            logical_name="所有者的测试文档",
            resource_type="文档",
        ),
    )
    return store, core, secret_ref


def _asset(inspection, kind: ActionSafetyAssetKind):
    return next(item for item in inspection.assets if item.kind is kind)


def _replace_setup(core: ApplicationCore, mutate) -> None:
    with core.uow_factory() as work:
        setup = work.action_safety_setups.get_for_action(PROJECT_ID, ACTION_ID)
        assert setup is not None
        work.action_safety_setups.replace(mutate(setup))
        work.commit()


def _persist_completed_recording(
    core: ApplicationCore,
    secret_ref: str,
    *,
    read_action: bool = False,
) -> None:
    events = _recording_events(read_action=read_action)
    flow_id = "view-owner-resource" if read_action else "modify-owner-resource"
    draft = FlowDraftProcessor().build(
        recording_id=RECORDING_ID,
        flow_id=flow_id,
        action_candidate_id=ACTION_ID,
        events=events,
    )
    reviewer = FlowDraftReviewer()
    targeted = reviewer.apply(
        draft,
        ConfirmFlowDraftTarget(
            schema_version="1",
            operation="CONFIRM_TARGET_STEP",
            step_id=draft.steps[0].id,
        ),
    )
    resource_candidate = next(
        item
        for item in targeted.steps[0].resource_candidates
        if item.location == "path[1]"
    )
    confirmed = reviewer.apply(
        targeted,
        ConfirmFlowDraftResource(
            schema_version="1",
            operation="CONFIRM_RESOURCE_SLOT",
            candidate_id=resource_candidate.candidate_id,
        ),
    )
    request = RecordingRunnerRequest(
        schema_version="1",
        recording_id=RECORDING_ID,
        project_id=PROJECT_ID,
        action_candidate_id=ACTION_ID,
        created_at_us=NOW_US,
        target_scope=WebTargetScope(
            base_url="http://127.0.0.1:18080",
            allowed_origins=("http://127.0.0.1:18080",),
            allowed_hosts=("127.0.0.1",),
            allowed_ports=(18080,),
            allow_private_network=True,
        ),
        sessions=(
            RecordingSessionRef(
                test_identity_id=IDENTITY_ID,
                session_ref="session_" + "6" * 32,
                auth_method=RecordingAuthMethod.BEARER,
                bearer_ref="env:RECORDING_BEARER",
                expires_at_us=NOW_US + 1_000_000,
            ),
        ),
        budget=RecordingBudget(max_duration_us=1_000_000, max_contexts=1),
        headless=False,
        trace_enabled=False,
    )
    request_hash, _ = core.recording_request_store.write(JOB_ID, request)
    recording = Recording(
        recording_id=RECORDING_ID,
        project_id=PROJECT_ID,
        state=RecordingState.PENDING_REVIEW,
        created_at_us=NOW_US,
        updated_at_us=NOW_US + 6,
        started_at_us=NOW_US + 2,
        capture_finished_at_us=NOW_US + 5,
        events=_recording_state_events(),
    )
    with core.uow_factory() as work:
        work.projects.add(
            ProjectRecord(
                project_id=PROJECT_ID,
                name="安全准备测试",
                status=ProjectStatus.DRAFT,
                created_at_us=NOW_US,
                updated_at_us=NOW_US,
            )
        )
        work.application_understanding.add(_understanding(read_action=read_action))
        work.test_identities.add(
            Identity(
                identity_id=IDENTITY_ID,
                project_id=PROJECT_ID,
                role_candidate_id=ROLE_ID,
                role_canonical_key="owner",
                role_display_name="所有者",
                label="所有者测试账号",
                confirmed_endpoint="http://127.0.0.1:18080",
                endpoint_source_fingerprint=ENDPOINT_FINGERPRINT,
                understanding_revision=3,
                auth_method=IdentityAuthMethod.BEARER,
                bearer_secret_ref=secret_ref,
                prepared_at_us=NOW_US + 1,
                refreshed_at_us=NOW_US + 1,
                created_at_us=NOW_US,
                updated_at_us=NOW_US + 1,
            )
        )
        work.recordings.add(
            RecordingRecord.from_domain(
                recording,
                flow_id=flow_id,
                browser_events=events,
            )
        )
        encoded = canonical_flow_draft_json_bytes(confirmed)
        work.flow_drafts.add(
            FlowDraftRevisionRecord(
                recording_id=RECORDING_ID,
                revision=confirmed.revision,
                flow_id=confirmed.flow_id,
                draft=confirmed,
                draft_sha256=hashlib.sha256(encoded).hexdigest(),
                created_at_us=NOW_US + 6,
            )
        )
        work.jobs.add(
            JobRecord(
                job_id=JOB_ID,
                project_id=PROJECT_ID,
                recording_id=RECORDING_ID,
                operation_type="BROWSER_RECORDING",
                state=JobState.SUCCEEDED,
                idempotency_key="safety-setup-recording",
                request_hash=request_hash,
                attempt=0,
                max_attempts=1,
                available_at_us=NOW_US,
                fencing_token=0,
                created_at_us=NOW_US,
                updated_at_us=NOW_US + 6,
            )
        )
        work.commit()
    RecordingLifecycle(core.uow_factory, var_dir=core.var_dir).finalize(
        RECORDING_ID,
        var_dir=core.var_dir,
        now_us=NOW_US + 7,
    )


def _understanding(*, read_action: bool = False) -> ApplicationUnderstanding:
    return ApplicationUnderstanding(
        project_id=PROJECT_ID,
        source_root="D:/sample",
        confirmed_endpoint="http://127.0.0.1:18080",
        endpoint_source_fingerprint=ENDPOINT_FINGERPRINT,
        endpoint_confirmed_at_us=NOW_US,
        endpoint_last_checked_at_us=NOW_US,
        endpoint_reachable=True,
        source_analysis_authorized=True,
        source_analysis_authorized_at_us=NOW_US,
        source_fingerprint=SOURCE_FINGERPRINT,
        analysis_completed_at_us=NOW_US,
        role_candidates=(
            RoleCandidate(
                candidate_id=ROLE_ID,
                canonical_key="owner",
                display_name="所有者",
                confidence=CandidateConfidence.HIGH,
                decision=CandidateDecision.CONFIRMED,
                origin=CandidateOrigin.MANUAL,
            ),
        ),
        action_candidates=(
            ActionCandidate(
                candidate_id=ACTION_ID,
                canonical_key=("view_owner_resource" if read_action else "modify_owner_resource"),
                display_name=("查看所有者资源" if read_action else "修改所有者资源"),
                confidence=CandidateConfidence.HIGH,
                risk_hint=(ActionRiskHint.READ if read_action else ActionRiskHint.WRITE),
                decision=CandidateDecision.CONFIRMED,
                origin=CandidateOrigin.MANUAL,
            ),
        ),
        revision=3,
        created_at_us=NOW_US,
        updated_at_us=NOW_US,
    )


def _recording_state_events() -> tuple[RecordingStateEvent, ...]:
    states = (
        RecordingState.CREATED,
        RecordingState.STARTING,
        RecordingState.RECORDING,
        RecordingState.CLEANING,
        RecordingState.PROCESSING,
        RecordingState.PENDING_REVIEW,
    )
    return tuple(
        RecordingStateEvent(
            sequence=index,
            source=source,
            target=target,
            operator="TEST_SETUP",
            occurred_at_us=NOW_US + index + 1,
        )
        for index, (source, target) in enumerate(pairwise(states), start=1)
    )


def _recording_events(*, read_action: bool = False) -> tuple[RecordingEvent, ...]:
    if read_action:
        requests = (
            (
                "GET",
                "request_000001",
                None,
                '{"project_id":"owner-resource","materials":[{"name":"说明"}]}',
            ),
        )
    else:
        requests = (
            ("PATCH", "request_000001", '{"value":"changed"}', "{}"),
            ("GET", "request_000002", None, '{"state":"changed"}'),
            ("PATCH", "request_000003", '{"value":"original"}', "{}"),
            ("GET", "request_000004", None, '{"state":"original"}'),
        )
    events: list[RecordingEvent] = []
    sequence = 1
    for method, request_id, body, response_body in requests:
        events.append(
            RecordingEvent(
                sequence=sequence,
                occurred_at_us=NOW_US + 10 + sequence,
                kind=RecordingEventKind.REQUEST,
                identity_id="recording-owner",
                page_id="page_000001",
                frame_id="frame_000001",
                request_id=request_id,
                url="http://127.0.0.1:18080/resources/owner-resource",
                method=method,
                resource_type="fetch",
                body=body,
            )
        )
        sequence += 1
        events.append(
            RecordingEvent(
                sequence=sequence,
                occurred_at_us=NOW_US + 10 + sequence,
                kind=RecordingEventKind.RESPONSE,
                identity_id="recording-owner",
                page_id="page_000001",
                frame_id="frame_000001",
                request_id=request_id,
                url="http://127.0.0.1:18080/resources/owner-resource",
                status_code=200,
                body=response_body,
            )
        )
        sequence += 1
    return tuple(events)
