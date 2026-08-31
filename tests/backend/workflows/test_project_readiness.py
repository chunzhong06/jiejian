# 验证项目就绪状态的确定性事实投影。

from __future__ import annotations

from product.backend.core.lifecycle import ProjectStatus
from product.backend.infra.storage import ExecutionProfileRecord, ProjectRecord
from product.backend.composition import ApplicationCore
from product.backend.workflows.projects.readiness import ProjectReadinessService
from product.protocols import TargetType

def _project(project_id: str, *, status: ProjectStatus) -> ProjectRecord:
    return ProjectRecord(
        project_id=project_id,
        name="演示应用",
        status=status,
        target_type=TargetType.WEB,
        created_at_us=1,
        updated_at_us=1,
    )

def test_draft_project_requires_application_connection(tmp_path) -> None:
    application = ApplicationCore(tmp_path / "var", environ={})
    try:
        with application.uow_factory() as work:
            work.projects.add(_project("draft-app", status=ProjectStatus.DRAFT))
            work.commit()

        view = application.project_readiness.get("draft-app")

        assert view.application_connected is False
        assert view.endpoint_status == "NEEDS_CONNECTION"
        assert view.next_required_action == "CONNECT_APPLICATION"
    finally:
        application.close()

def test_generated_profile_cannot_replace_application_connection(tmp_path) -> None:
    application = ApplicationCore(tmp_path / "var", environ={})
    try:
        with application.uow_factory() as work:
            work.projects.add(_project("profile-only-app", status=ProjectStatus.READY))
            work.execution_profiles.add(
                ExecutionProfileRecord(
                    profile_id="legacy-profile",
                    project_id="profile-only-app",
                    source_path=str(tmp_path / "profile.json"),
                    source_hash="a" * 64,
                    contract_id="legacy-contract",
                    contract_version=1,
                    contract_fingerprint="b" * 64,
                    plan_fingerprint="c" * 64,
                    engine_version="test",
                    created_at_us=1,
                    updated_at_us=1,
                )
            )
            work.commit()

        view = ProjectReadinessService(application.uow_factory).get("profile-only-app")

        assert view.application_connected is False
        assert view.endpoint_status == "NEEDS_CONNECTION"
        assert view.source_analysis_status == "NOT_AVAILABLE"
        assert view.execution_profile_available is True
        assert view.current_scope_runnable is False
        assert view.next_required_action == "CONNECT_APPLICATION"
    finally:
        application.close()
