# 验证 SecuritySetupCompiler 的整体确定性编译与注册闭环。

from pathlib import Path
import pytest
from product.backend.core.application_understanding import (
    CandidateConfidence,
    CandidateDecision,
    CandidateOrigin,
    RoleCandidate,
)
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.permission_intent import PermissionIntentRelation
from product.backend.core.test_identity import (
    TestIdentity as IdentityRecord,
    TestIdentityAuthMethod as IdentityAuthMethod,
)
from product.backend.core.verification.permissions import PermissionExpectation
from product.backend.workflows.context import ApplicationCore
from product.protocols import HttpPredicateKind
from product.protocols.web.profile import parse_web_execution_profile
from tests.backend.workflows.recording.test_action_safety_setup import (
    ACTION_ID,
    ENDPOINT_FINGERPRINT,
    IDENTITY_ID,
    NOW_US,
    PROJECT_ID,
    RECORDING_ID,
    ROLE_ID,
    _FakeSecretStore,
    _confirmation,
    _persist_completed_recording,
)
pytestmark = pytest.mark.database
PEER_IDENTITY_ID = "tid_" + "7" * 32
REPLACEMENT_IDENTITY_ID = "tid_" + "6" * 32
OTHER_ROLE_ID = "role_" + "8" * 32
OTHER_IDENTITY_ID = "tid_" + "6" * 32
OTHER_LATER_IDENTITY_ID = "tid_" + "9" * 32

def test_compiler_is_deterministic_and_rejects_profile_after_authority_change(
    tmp_path: Path,
) -> None:
    store = _FakeSecretStore()
    owner_ref = f"cred:jiejian/test-identity/{PROJECT_ID}/{IDENTITY_ID}/bearer"
    peer_ref = f"cred:jiejian/test-identity/{PROJECT_ID}/{PEER_IDENTITY_ID}/bearer"
    store.write(owner_ref, "owner-secret")
    store.write(peer_ref, "peer-secret")
    core = ApplicationCore(
        tmp_path / "var",
        secret_store=store,
        clock_us=lambda: NOW_US + 100,
    )
    try:
        _persist_completed_recording(core, owner_ref)
        preview = core.action_safety_setup.preview(RECORDING_ID)
        core.action_safety_setup.confirm(
            RECORDING_ID,
            _confirmation(preview, include_recovery=True),
        )
        with core.uow_factory() as work:
            work.test_identities.add(
                IdentityRecord(
                    identity_id=PEER_IDENTITY_ID,
                    project_id=PROJECT_ID,
                    role_candidate_id=ROLE_ID,
                    role_canonical_key="owner",
                    role_display_name="所有者",
                    label="同角色其他测试账号",
                    confirmed_endpoint="http://127.0.0.1:18080",
                    endpoint_source_fingerprint=ENDPOINT_FINGERPRINT,
                    understanding_revision=3,
                    auth_method=IdentityAuthMethod.BEARER,
                    bearer_secret_ref=peer_ref,
                    prepared_at_us=NOW_US + 1,
                    refreshed_at_us=NOW_US + 1,
                    created_at_us=NOW_US,
                    updated_at_us=NOW_US + 1,
                )
            )
            work.commit()

        core.permission_intents.confirm(
            PROJECT_ID,
            ACTION_ID,
            ROLE_ID,
            ROLE_ID,
            PermissionIntentRelation.OWNS,
            expectation=PermissionExpectation.ALLOW,
            actor="测试用户",
        )
        core.permission_intents.confirm(
            PROJECT_ID,
            ACTION_ID,
            ROLE_ID,
            ROLE_ID,
            PermissionIntentRelation.SAME_ROLE_OTHER_ACCOUNT,
            expectation=PermissionExpectation.DENY,
            actor="测试用户",
        )

        before_compile = core.project_readiness.get(PROJECT_ID)
        assert before_compile.permission_actions[0].compilable is True
        assert before_compile.current_scope_runnable is False

        first = core.security_setup.compile(PROJECT_ID, actor="测试用户")
        second = core.security_setup.compile(PROJECT_ID, actor="测试用户")

        assert second.reused is True
        assert second.authority_fingerprint == first.authority_fingerprint
        assert second.contract_id == first.contract_id
        assert second.contract_version == first.contract_version
        assert second.contract_fingerprint == first.contract_fingerprint
        assert second.profile_id == first.profile_id
        assert second.profile_path == first.profile_path
        assert second.profile_sha256 == first.profile_sha256
        assert Path(first.profile_path).is_relative_to(
            core.var_dir
            / "data"
            / "projects"
            / PROJECT_ID
            / "execution"
            / "generated"
        )
        profile_text = Path(first.profile_path).read_text(encoding="utf-8")
        assert Path(first.profile_path).stem == first.profile_sha256
        assert "owner-secret" not in profile_text
        assert "peer-secret" not in profile_text
        assert "env:JIEJIAN_TEST_IDENTITY_" in profile_text
        profile = parse_web_execution_profile(Path(first.profile_path).read_bytes())
        assert len(profile.observers) == 1
        assert profile.observers[0].observer_type.value == "OWNER_API"
        target_step = profile.workflow_bindings[0].steps[0]
        assert {
            status
            for predicate in target_step.classifier.denied
            if predicate.kind is HttpPredicateKind.STATUS_IN
            for status in predicate.statuses
        } == {401, 403, 404}
        core.execution.build_request(first.profile_id, project_id=PROJECT_ID)
        ready = core.project_readiness.get(PROJECT_ID)
        assert ready.current_scope_runnable is True
        assert ready.remaining_gap_count == 0

        with core.uow_factory() as work:
            understanding = work.application_understanding.get(PROJECT_ID)
            assert understanding is not None
            work.application_understanding.replace(
                understanding.model_copy(
                    update={
                        "source_fingerprint": "c" * 64,
                        "revision": understanding.revision + 1,
                        "updated_at_us": understanding.updated_at_us + 1,
                    }
                )
            )
            work.commit()

        with pytest.raises(JiejianError) as stale:
            core.execution.build_request(first.profile_id, project_id=PROJECT_ID)
        assert stale.value.code == ErrorCode.EXECUTION_PROFILE_SOURCE_DRIFT.value
        changed = core.project_readiness.get(PROJECT_ID)
        assert changed.current_scope_runnable is False
    finally:
        core.close()
