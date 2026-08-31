# 验证源码快照、真实增删改、权威修复引用、权限实现影响和 Oracle 不变量。

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from product.backend.core.application_understanding import (
    ActionCandidate,
    ActionRiskHint,
    CandidateConfidence,
    CandidateEvidence,
    CandidateOrigin,
    RoleCandidate,
)
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.permission_intent import IntentImplementationBindingStatus
from product.backend.core.repair import RepairContractReference
from product.backend.core.source_changes import (
    ChangeManifest,
    SourceFileFingerprint,
    source_fingerprint,
)
from product.backend.workflows.application_understanding.analysis.models import (
    ApplicationAnalysisResult,
)
from product.backend.workflows.application_understanding.endpoints import (
    EndpointProbeObservation,
    TargetEndpointDiscovery,
)
from product.backend.workflows.context import ApplicationCore
from tests.backend.workflows.recording.test_action_safety_setup import (
    ACTION_ID,
    NOW_US,
    PROJECT_ID,
    ROLE_ID,
)
from tests.backend.workflows.security_setup.test_checks import _prepared_core


pytestmark = pytest.mark.database


def test_manifest_rejects_absolute_parent_and_empty_path_segments() -> None:
    for path in ("../outside.py", "/absolute.py", "C:/outside.py", "src//app.py"):
        with pytest.raises(ValueError):
            ChangeManifest(
                change_id="chg_" + "1" * 32,
                project_id="example-project",
                reason="完成业务修改",
                claimed_paths=(path,),
                submitted_by="Agent",
                created_at_us=1,
            )


def test_same_source_fingerprint_is_idempotent_and_mtime_is_ignored(
    tmp_path: Path,
) -> None:
    core, project_id, source = _connected_core(tmp_path)
    source_file = source / "app.py"
    source_file.write_text(
        "roles = ['owner']\n@app.get('/documents')\ndef documents(): pass\n",
        encoding="utf-8",
    )
    try:
        first = _authorize_and_analyze(core, project_id)
        with core.uow_factory() as work:
            first_snapshot = work.source_changes.snapshot_for_fingerprint(
                project_id,
                str(first.source_fingerprint),
            )
        stat = source_file.stat()
        os.utime(source_file, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000))
        second = core.application_understanding.analyze_source(
            project_id,
            revision=first.revision,
        )
        with core.uow_factory() as work:
            second_snapshot = work.source_changes.snapshot_for_fingerprint(
                project_id,
                str(second.source_fingerprint),
            )
        assert second.source_fingerprint == first.source_fingerprint
        assert first_snapshot == second_snapshot
        assert first_snapshot is not None
        assert first_snapshot.understanding_revision == first.revision
    finally:
        core.close()


def test_repair_reference_is_verified_persisted_and_carried_into_revalidation(
    tmp_path: Path,
) -> None:
    core, project_id, source = _connected_core(tmp_path)
    try:
        first = _authorize_and_analyze(core, project_id)
        (source / "app.py").write_text(
            "roles = ['owner']\n@app.get('/documents')\ndef documents(): return []\n",
            encoding="utf-8",
        )
        reference = RepairContractReference(
            source_run_id="run_" + "1" * 32,
            source_finding_id="finding_" + "2" * 32,
            repair_fingerprint="3" * 64,
        )
        verified: list[tuple[str, RepairContractReference]] = []
        core.source_changes._repair_contracts = SimpleNamespace(
            verify_reference=lambda checked_project, checked_reference: verified.append(
                (checked_project, checked_reference)
            )
        )

        manifest, _, _ = core.source_changes.submit(
            project_id,
            reason="验证修复后的实现",
            submitted_by="MCP Agent",
            repair_reference=reference,
        )

        stored, _, _ = core.source_changes.get(manifest.change_id)
        plan = core.source_changes.revalidation_plan(project_id, manifest.change_id)
        assert first.source_fingerprint is not None
        assert verified == [(project_id, reference)]
        assert stored.repair_reference == reference
        assert plan.repair_reference == reference
    finally:
        core.close()


def test_actual_diff_reports_add_modify_remove_and_ignores_manifest_omission(
    tmp_path: Path,
) -> None:
    core, project_id, source = _connected_core(tmp_path)
    (source / "modify.py").write_text("value = 1\n", encoding="utf-8")
    (source / "remove.py").write_text("removed = True\n", encoding="utf-8")
    (source / "keep.py").write_text("kept = True\n", encoding="utf-8")
    try:
        _authorize_and_analyze(core, project_id)
        (source / "modify.py").write_text("value = 2\n", encoding="utf-8")
        (source / "remove.py").unlink()
        (source / "added.py").write_text("added = True\n", encoding="utf-8")

        manifest, change_set, assessment = core.source_changes.submit(
            project_id,
            reason="调整实现",
            claimed_paths=("keep.py",),
            submitted_by="Agent",
        )

        assert manifest.claimed_paths == ("keep.py",)
        assert change_set.status == "COMPARABLE"
        assert change_set.added_paths == ("added.py",)
        assert change_set.modified_paths == ("modify.py",)
        assert change_set.removed_paths == ("remove.py",)
        assert assessment.complete is True
        assert assessment.impacts == ()
    finally:
        core.close()


def test_first_change_without_baseline_is_incomplete_and_never_optimistic(
    tmp_path: Path,
) -> None:
    core, project_id, source = _connected_core(tmp_path)
    (source / "app.py").write_text("value = 1\n", encoding="utf-8")
    try:
        current = core.application_understanding.get(project_id)
        current = core.application_understanding.authorize_source_analysis(
            project_id,
            revision=current.revision,
        )
        _, change_set, assessment = core.source_changes.submit(
            project_id,
            reason="首次提交变化",
            submitted_by="Agent",
        )
        assert current.source_fingerprint is None
        assert change_set.status == "NO_BASELINE"
        assert change_set.changed_paths == ()
        assert assessment.complete is False
        assert assessment.reason_codes == ("NO_BASELINE",)
        assert all(
            item.classification != "NO_DIRECT_EVIDENCE"
            for item in assessment.impacts
        )
    finally:
        core.close()


@pytest.mark.parametrize(
    ("changed_path", "expected_classification", "expected_reason"),
    (
        ("action.py", "DIRECTLY_AFFECTED", "ACTION_EVIDENCE_CHANGED"),
        ("role.py", "DIRECTLY_AFFECTED", "SUBJECT_EVIDENCE_CHANGED"),
        ("other.py", "NO_DIRECT_EVIDENCE", "NO_DIRECT_IMPLEMENTATION_EVIDENCE"),
    ),
)
def test_current_binding_uses_action_and_role_evidence_only(
    tmp_path: Path,
    changed_path: str,
    expected_classification: str,
    expected_reason: str,
) -> None:
    core = _prepared_core(tmp_path)
    try:
        baseline = _analysis_result()
        core.application_understanding.analyzer = _StaticAnalyzer(baseline)
        current = core.application_understanding.get(PROJECT_ID)
        analyzed = core.application_understanding.analyze_source(
            PROJECT_ID,
            revision=current.revision,
        )
        oracle_before = _oracle(core)

        changed_hashes = {
            item.relative_path: item.content_sha256 for item in baseline.files
        }
        changed_hashes[changed_path] = _sha(f"changed:{changed_path}")
        changed = _analysis_result(changed_hashes)
        core.application_understanding.analyzer = _StaticAnalyzer(changed)
        _, change_set, assessment = core.source_changes.submit(
            PROJECT_ID,
            reason="修改实现",
            claimed_paths=("unrelated.py",),
            submitted_by="Agent",
        )

        assert change_set.modified_paths == (changed_path,)
        assert assessment.complete is True
        assert {item.classification for item in assessment.impacts} == {
            expected_classification
        }
        assert all(expected_reason in item.reason_codes for item in assessment.impacts)
        if expected_classification == "NO_DIRECT_EVIDENCE":
            assert all(
                item.message == "当前没有发现直接实现关联"
                for item in assessment.impacts
            )
        assert _oracle(core) == oracle_before
        assert core.application_understanding.get(PROJECT_ID).revision == analyzed.revision + 1
    finally:
        core.close()


def test_stale_candidate_requires_mapping_review_without_changing_oracle(
    tmp_path: Path,
) -> None:
    core = _prepared_core(tmp_path)
    try:
        baseline = _analysis_result()
        core.application_understanding.analyzer = _StaticAnalyzer(baseline)
        current = core.application_understanding.get(PROJECT_ID)
        core.application_understanding.analyze_source(
            PROJECT_ID,
            revision=current.revision,
        )
        with core.uow_factory() as work:
            detected = work.application_understanding.get(PROJECT_ID)
            assert detected is not None
            work.application_understanding.replace(
                detected.model_copy(
                    update={
                        "action_candidates": tuple(
                            item.model_copy(update={"origin": CandidateOrigin.DETECTED})
                            for item in detected.action_candidates
                        )
                    }
                )
            )
            work.commit()
        oracle_before = _oracle(core)

        files = tuple(item for item in baseline.files if item.relative_path != "action.py")
        stale = ApplicationAnalysisResult(
            source_fingerprint=source_fingerprint(files),
            files=files,
            role_candidates=baseline.role_candidates,
            action_candidates=(),
            files_read=len(files),
            total_bytes=len(files),
        )
        core.application_understanding.analyzer = _StaticAnalyzer(stale)
        _, change_set, assessment = core.source_changes.submit(
            PROJECT_ID,
            reason="删除动作实现",
            submitted_by="Agent",
        )

        assert change_set.removed_paths == ("action.py",)
        assert {item.classification for item in assessment.impacts} == {
            "MAPPING_REVIEW_REQUIRED"
        }
        assert all("BINDING_NOT_CURRENT" in item.reason_codes for item in assessment.impacts)
        assert _oracle(core) == oracle_before
    finally:
        core.close()


def test_current_manual_mapping_without_evidence_requires_review(tmp_path: Path) -> None:
    core = _prepared_core(tmp_path)
    try:
        baseline_files = (
            SourceFileFingerprint(
                relative_path="other.py",
                content_sha256=_sha("other"),
            ),
        )
        baseline = ApplicationAnalysisResult(
            source_fingerprint=source_fingerprint(baseline_files),
            files=baseline_files,
            role_candidates=(),
            action_candidates=(),
            files_read=1,
            total_bytes=1,
        )
        core.application_understanding.analyzer = _StaticAnalyzer(baseline)
        current = core.application_understanding.get(PROJECT_ID)
        core.application_understanding.analyze_source(
            PROJECT_ID,
            revision=current.revision,
        )
        changed_files = (
            SourceFileFingerprint(
                relative_path="other.py",
                content_sha256=_sha("changed-other"),
            ),
        )
        core.application_understanding.analyzer = _StaticAnalyzer(
            ApplicationAnalysisResult(
                source_fingerprint=source_fingerprint(changed_files),
                files=changed_files,
                role_candidates=(),
                action_candidates=(),
                files_read=1,
                total_bytes=1,
            )
        )

        manifest, _, assessment = core.source_changes.submit(
            PROJECT_ID,
            reason="修改其他实现",
            submitted_by="Agent",
        )

        assert {item.classification for item in assessment.impacts} == {
            "MAPPING_REVIEW_REQUIRED"
        }
        assert all(
            "IMPLEMENTATION_EVIDENCE_MISSING" in item.reason_codes
            for item in assessment.impacts
        )
        before_epoch = core.permission_intents.matrix(PROJECT_ID).policy_epoch
        with pytest.raises(JiejianError) as blocked:
            core.source_changes.revalidation_plan(PROJECT_ID, manifest.change_id)
        assert blocked.value.code == ErrorCode.STATE_PRECONDITION.value

        with core.uow_factory() as work:
            revisions = work.permission_intents.list_latest(PROJECT_ID)
            bindings = tuple(
                work.permission_intents.binding(revision.intent_id, revision.revision)
                for revision in revisions
            )
        assert all(binding is not None for binding in bindings)
        for revision, binding in zip(revisions, bindings, strict=True):
            assert binding is not None
            proposal = core.permission_intents.propose_rebind_target(
                PROJECT_ID,
                revision.intent_id,
                action_candidate_id=binding.action_candidate_id,
                subject_role_candidate_id=binding.subject_role_candidate_id,
                resource_owner_role_candidate_id=binding.resource_owner_role_candidate_id,
                proposed_by="MCP Agent",
                reason="建议确认缺少静态证据的既有实现映射",
            )
            core.permission_intents.approve_proposal(
                PROJECT_ID,
                proposal.proposal_id,
                reason="用户确认实现映射",
            )
        plan = core.source_changes.revalidation_plan(PROJECT_ID, manifest.change_id)

        assert plan.required_intent_ids == tuple(
            sorted(revision.intent_id for revision in revisions)
        )
        assert core.permission_intents.matrix(PROJECT_ID).policy_epoch == before_epoch
    finally:
        core.close()


def test_change_revalidation_plan_freezes_into_run_without_narrowing_coverage(
    tmp_path: Path,
) -> None:
    core = _prepared_core(tmp_path)
    try:
        baseline = _analysis_result()
        core.application_understanding.analyzer = _StaticAnalyzer(baseline)
        current = core.application_understanding.get(PROJECT_ID)
        core.application_understanding.analyze_source(
            PROJECT_ID,
            revision=current.revision,
        )
        changed_hashes = {
            item.relative_path: item.content_sha256 for item in baseline.files
        }
        changed_hashes["action.py"] = _sha("changed:action.py")
        core.application_understanding.analyzer = _StaticAnalyzer(
            _analysis_result(changed_hashes)
        )
        manifest, _, assessment = core.source_changes.submit(
            PROJECT_ID,
            reason="Agent 完成动作实现修复",
            claimed_paths=("other.py",),
            submitted_by="MCP Agent",
        )

        before_epoch = core.permission_intents.matrix(PROJECT_ID).policy_epoch
        plan = core.source_changes.revalidation_plan(PROJECT_ID, manifest.change_id)
        assert plan.impact_fingerprint == assessment.impact_fingerprint
        assert len(plan.required_intent_ids) == 2
        assert plan.full_active_scope is True

        preview = core.checks.prepare(PROJECT_ID, change_id=manifest.change_id)
        assert preview.change_id == manifest.change_id
        assert preview.required_intent_count == len(plan.required_intent_ids)
        assert preview.ready is True
        submission, request, _ = core.checks.submit(
            PROJECT_ID,
            change_id=manifest.change_id,
            idempotency_key="change-revalidation-run",
        )

        assert submission.run.project_id == PROJECT_ID
        assert request.change_context is not None
        assert request.change_context.change_id == manifest.change_id
        assert request.change_context.impact_fingerprint == assessment.impact_fingerprint
        assert request.change_context.required_intent_ids == plan.required_intent_ids
        assert request.change_context.source_fingerprint == plan.source_fingerprint
        assert len(request.project_snapshot.plan.cases) == 2
        persisted = core.execution_request_store.load(
            submission.job.job_id,
            expected_hash=submission.job.request_hash,
        )
        assert persisted.change_context == request.change_context
        assert core.permission_intents.matrix(PROJECT_ID).policy_epoch == before_epoch
        payload = core.source_changes.view(manifest.change_id).model_dump(mode="json")
        assert payload["actual_changed_path_count"] == 1
        assert payload["claimed_paths"] == ["other.py"]
        assert payload["modified_paths"] == ["action.py"]
        assert "source_fingerprint" not in payload
        assert "impact_fingerprint" not in payload
        assert "changed_paths" not in payload
    finally:
        core.close()


def test_change_revalidation_waits_for_human_approved_rebind_without_epoch_change(
    tmp_path: Path,
) -> None:
    core = _prepared_core(tmp_path)
    try:
        baseline = _analysis_result()
        core.application_understanding.analyzer = _StaticAnalyzer(baseline)
        current = core.application_understanding.get(PROJECT_ID)
        core.application_understanding.analyze_source(
            PROJECT_ID,
            revision=current.revision,
        )
        changed_hashes = {
            item.relative_path: item.content_sha256 for item in baseline.files
        }
        changed_hashes["action.py"] = _sha("rebind:action.py")
        core.application_understanding.analyzer = _StaticAnalyzer(
            _analysis_result(changed_hashes)
        )
        manifest, _, _ = core.source_changes.submit(
            PROJECT_ID,
            reason="Agent 调整动作实现",
            submitted_by="MCP Agent",
        )
        before_epoch = core.permission_intents.matrix(PROJECT_ID).policy_epoch
        with core.uow_factory() as work:
            revision = work.permission_intents.list_latest(PROJECT_ID)[0]
            binding = work.permission_intents.binding(
                revision.intent_id,
                revision.revision,
            )
            assert binding is not None
            work.permission_intents.replace_binding(
                binding.model_copy(
                    update={
                        "status": IntentImplementationBindingStatus.NEEDS_REVIEW,
                        "reason_codes": ("IMPLEMENTATION_EVIDENCE_CHANGED",),
                    }
                )
            )
            work.commit()

        with pytest.raises(JiejianError) as blocked:
            core.source_changes.revalidation_plan(PROJECT_ID, manifest.change_id)
        assert blocked.value.code == ErrorCode.STATE_PRECONDITION.value
        assert blocked.value.to_dict()["details"]["next_path"] == "/permissions"

        proposal = core.permission_intents.propose_rebind_target(
            PROJECT_ID,
            revision.intent_id,
            action_candidate_id=binding.action_candidate_id,
            subject_role_candidate_id=binding.subject_role_candidate_id,
            resource_owner_role_candidate_id=binding.resource_owner_role_candidate_id,
            proposed_by="MCP Agent",
            reason="建议把当前实现重新绑定到原权限要求",
        )
        approved = core.permission_intents.approve_proposal(
            PROJECT_ID,
            proposal.proposal_id,
            reason="用户确认实现映射",
        )
        plan = core.source_changes.revalidation_plan(PROJECT_ID, manifest.change_id)

        assert approved.status.value == "APPROVED"
        assert revision.intent_id in plan.required_intent_ids
        assert core.permission_intents.matrix(PROJECT_ID).policy_epoch == before_epoch
    finally:
        core.close()


def _connected_core(tmp_path: Path) -> tuple[ApplicationCore, str, Path]:
    source = tmp_path / "source"
    source.mkdir()
    endpoint = "http://127.0.0.1:4666"

    def probe(candidate, _limits):
        return EndpointProbeObservation(
            reachable=candidate == endpoint,
            status_code=200 if candidate == endpoint else None,
            detail="测试服务已响应" if candidate == endpoint else "测试服务未响应",
        )

    core = ApplicationCore(
        tmp_path / "var",
        environ={},
        endpoint_discovery=TargetEndpointDiscovery(probe=probe),
    )
    connection = core.application_understanding.connect(source)
    confirmed = core.application_understanding.confirm_endpoint(
        connection.project.project_id,
        endpoint=endpoint,
        revision=connection.understanding.revision,
    )
    assert confirmed.confirmed_endpoint == endpoint
    return core, connection.project.project_id, source


def _authorize_and_analyze(core: ApplicationCore, project_id: str):
    current = core.application_understanding.get(project_id)
    current = core.application_understanding.authorize_source_analysis(
        project_id,
        revision=current.revision,
    )
    return core.application_understanding.analyze_source(
        project_id,
        revision=current.revision,
    )


def _analysis_result(
    hashes: dict[str, str] | None = None,
) -> ApplicationAnalysisResult:
    resolved = hashes or {
        "action.py": _sha("action"),
        "other.py": _sha("other"),
        "role.py": _sha("role"),
    }
    files = tuple(
        SourceFileFingerprint(relative_path=path, content_sha256=digest)
        for path, digest in sorted(resolved.items())
    )
    action_hash = resolved.get("action.py", _sha("removed-action"))
    role_hash = resolved.get("role.py", _sha("removed-role"))
    return ApplicationAnalysisResult(
        source_fingerprint=source_fingerprint(files),
        files=files,
        role_candidates=(
            RoleCandidate(
                candidate_id=ROLE_ID,
                canonical_key="owner",
                display_name="所有者",
                confidence=CandidateConfidence.HIGH,
                evidence=(
                    CandidateEvidence(
                        relative_path="role.py",
                        line_start=1,
                        line_end=1,
                        detector="test-role",
                        content_sha256=role_hash,
                    ),
                ),
            ),
        ),
        action_candidates=(
            ActionCandidate(
                candidate_id=ACTION_ID,
                canonical_key="modify_owner_resource",
                display_name="修改所有者资源",
                confidence=CandidateConfidence.HIGH,
                risk_hint=ActionRiskHint.WRITE,
                evidence=(
                    CandidateEvidence(
                        relative_path="action.py",
                        line_start=1,
                        line_end=1,
                        detector="test-action",
                        content_sha256=action_hash,
                    ),
                ),
            ),
        ),
        files_read=len(files),
        total_bytes=len(files),
    )


class _StaticAnalyzer:
    def __init__(self, result: ApplicationAnalysisResult) -> None:
        self._result = result

    def analyze(self, _project_id: str, _source_root: str) -> ApplicationAnalysisResult:
        return self._result


def _oracle(core: ApplicationCore) -> tuple[int, tuple[tuple[str, int, str], ...]]:
    with core.uow_factory() as work:
        state = work.permission_intents.policy_state(PROJECT_ID)
        revisions = work.permission_intents.list_latest(PROJECT_ID)
    return (
        0 if state is None else state.policy_epoch,
        tuple((item.intent_id, item.revision, item.intent_hash) for item in revisions),
    )


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
