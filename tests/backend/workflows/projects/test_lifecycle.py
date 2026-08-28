# 验证 Project ARCHIVED 对 Run、Recording、Job 与官方 Sample 活动态统一 fail-closed。

from __future__ import annotations

from types import SimpleNamespace

import pytest

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import JobState, ProjectStatus, RunLifecycle
from product.backend.core.recording import RecordingState
from product.backend.infra.storage import ProjectRecord
from product.backend.workflows.projects.lifecycle import ProjectLifecycleService


class _Projects:
    def __init__(self, project: ProjectRecord) -> None:
        self.project = project

    def get(self, project_id: str) -> ProjectRecord | None:
        return self.project if self.project.project_id == project_id else None

    def replace(self, project: ProjectRecord) -> None:
        self.project = project


class _Work:
    def __init__(self, project: ProjectRecord, active: str | None) -> None:
        self.projects = _Projects(project)
        self.runs = SimpleNamespace(
            list_for_project=lambda _project_id: (
                (SimpleNamespace(run_id="run-active", lifecycle=RunLifecycle.RUNNING),)
                if active == "run"
                else ()
            )
        )
        self.recordings = SimpleNamespace(
            list_for_project=lambda _project_id: (
                (SimpleNamespace(recording_id="rec-active", state=RecordingState.RECORDING),)
                if active == "recording"
                else ()
            )
        )
        self.jobs = SimpleNamespace(
            list_for_project=lambda _project_id: (
                (SimpleNamespace(job_id="job-active", state=JobState.PENDING),)
                if active == "job"
                else ()
            )
        )
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_arguments) -> None:
        return None

    def commit(self) -> None:
        self.committed = True


class _Identities:
    def __init__(self) -> None:
        self.cleaned: list[str] = []

    def remove_project_credentials(self, project_id: str) -> int:
        self.cleaned.append(project_id)
        return 1


@pytest.mark.parametrize("active", ["run", "recording", "job", "official-sample"])
def test_archive_rejects_every_active_execution_boundary(active: str) -> None:
    work = _Work(
        ProjectRecord(
            project_id="sample-project",
            name="Sample",
            status=ProjectStatus.DRAFT,
            created_at_us=1,
            updated_at_us=1,
        ),
        active,
    )
    identities = _Identities()
    service = ProjectLifecycleService(
        lambda: work,
        identities,  # type: ignore[arg-type]
        official_sample_active=lambda _project_id: active == "official-sample",
        clock_us=lambda: 2,
    )

    with pytest.raises(JiejianError) as error:
        service.archive("sample-project")

    assert error.value.code == ErrorCode.PROJECT_ARCHIVE_CONFLICT.value
    assert identities.cleaned == []
    assert work.projects.project.status is ProjectStatus.DRAFT


def test_archive_cleans_credentials_and_only_changes_project_status() -> None:
    project = ProjectRecord(
        project_id="sample-project",
        name="Sample",
        status=ProjectStatus.READY,
        governed_contract_id="contract",
        governed_contract_version=1,
        created_at_us=1,
        updated_at_us=1,
    )
    work = _Work(project, None)
    identities = _Identities()
    service = ProjectLifecycleService(
        lambda: work,
        identities,  # type: ignore[arg-type]
        official_sample_active=lambda _project_id: False,
        clock_us=lambda: 2,
    )

    archived = service.archive("sample-project")

    assert archived.status is ProjectStatus.ARCHIVED
    assert archived.governed_contract_id == "contract"
    assert identities.cleaned == ["sample-project"]
    assert work.projects.project == archived
    assert work.committed is True
