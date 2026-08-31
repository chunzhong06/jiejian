# 验证项目就绪状态的确定性事实投影。

from __future__ import annotations

import pytest

from product.backend.core.lifecycle import ProjectStatus
from product.backend.infra.storage import ExecutionProfileRecord, ProjectRecord
from product.backend.composition import ApplicationCore
from product.backend.workflows.projects.preparation import (
    PreparationExternalBlockerView,
    ProjectPreparationView,
)
from product.backend.workflows.projects.readiness import ProjectReadinessService
from product.protocols import TargetType
from tests.backend.workflows.recording.test_action_safety_setup import PROJECT_ID
from tests.backend.workflows.security_setup.test_checks import _prepared_core

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


@pytest.mark.parametrize(
    ("category", "expected_action", "next_path"),
    (
        ("SOURCE_CHANGE", "REVIEW_CHANGE", "/changes"),
        ("PERMISSION", "REVIEW_PERMISSION", "/permissions"),
    ),
)
def test_external_blockers_map_to_distinct_next_actions(
    tmp_path,
    category: str,
    expected_action: str,
    next_path: str,
) -> None:
    application = _prepared_core(tmp_path)
    try:
        blocker = PreparationExternalBlockerView(
            key=f"{category.lower()}-blocker",
            category=category,
            label="需要用户处理",
            description="当前事实尚未形成可运行状态。",
            next_path=next_path,
            next_label="去处理",
            reason_codes=(f"{category}_BLOCKED",),
        )
        preparation = ProjectPreparationView(
            project_id=PROJECT_ID,
            ready=False,
            items=(),
            auto_action_count=0,
            user_action_count=0,
            blocked_count=0,
            external_blockers=(blocker,),
        )
        application.project_readiness._preparation_resolver = lambda _project_id: preparation
        application.project_readiness._endpoint_status_resolver = lambda _understanding: "CONFIRMED"

        view = application.project_readiness.get(PROJECT_ID)

        assert view.next_required_action == expected_action
    finally:
        application.close()
