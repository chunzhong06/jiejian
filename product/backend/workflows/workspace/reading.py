# 按工作区协调者要求读取已有事实；只读核对来源，保留原分支的读取时机，不创建任务或结论。
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import dataclass
from collections.abc import Callable
from typing import TYPE_CHECKING
from product.backend.core.development import DevelopmentTask
if TYPE_CHECKING:
    from product.backend.workflows.checks.service import CheckService
    from product.backend.workflows.checks.reading.results import CheckResultReader, CheckRunStatus
    from product.backend.workflows.changes.service import CurrentSourceChangeService
    from product.backend.workflows.projects.repair import CurrentProjectRepairService, ProjectRepair
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.recording.models import RecordingPurpose, RecordingState
from product.backend.workflows.recording.source import require_persisted_recording_source
from product.backend.workflows.preparation.models import PreparationStatus
from product.backend.workflows.workspace.models import WorkspaceLatestResult, WorkspaceSourceChange, WorkspaceDevelopment
from product.backend.workflows.checks.reading.story_text import JUDGEMENTS


@dataclass(frozen=True, slots=True)
class WorkspaceCheckReaders:
    checks: CheckService
    reader: CheckResultReader
    changes: CurrentSourceChangeService
    repairs: CurrentProjectRepairService
    source_inspector: Callable[[str], str]


@dataclass(frozen=True, slots=True)
class WorkspaceCheckFacts:
    active_check: CheckRunStatus | None
    source_change: WorkspaceSourceChange | None
    repair: ProjectRepair
    latest_result: WorkspaceLatestResult | None


@dataclass(frozen=True, slots=True)
class WorkspaceDevelopmentFacts:
    task: DevelopmentTask
    view: dict
    delivery: dict | None
    verification: dict | None


class WorkspaceReader:
    def __init__(self, uow_factory, *, var_dir, current_checks=None, development=None):
        self._uow_factory, self._var_dir = uow_factory, var_dir
        self.current_checks, self.development = current_checks, development

    def validate_connections(self):
        if self.current_checks is None or self.development is None:
            raise ValueError("生产工作区的检查与开发读取者尚未连接")

    def project(self, project_id):
        with self._uow_factory() as work:
            project = work.projects.get(project_id)
            understanding = work.application_understanding.get(project_id)
        if project is None:
            raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, "项目不存在")
        if understanding is None:
            raise JiejianError(
                ErrorCode.APPLICATION_UNDERSTANDING_NOT_FOUND,
                "应用理解记录不存在",
            )

        return project, understanding

    def checks(self, project_id, boundary, understanding):
        ports = self.current_checks
        reader, changes, repairs = ports.reader, ports.changes, ports.repairs
        latest_result, source_change = None, None
        active_check = reader.active_for_project(project_id)
        change = changes.latest(project_id)
        if change is not None:
            source_change = WorkspaceSourceChange(change_id=change.manifest.change_id,
                revalidation_status=change.revalidation.status,can_execute=change.revalidation.can_execute,
                reason=change.manifest.reason,created_at_us=change.manifest.created_at_us,
                submitted_by=change.manifest.submitted_by)
        repair = repairs.evaluate(project_id)
        for entry in reader.list_for_project(project_id):
            if entry.result_integrity != "VALID" or entry.run.policy_epoch != boundary.policy_epoch:
                continue
            package = reader.package(entry.run.run_id,project_id=project_id)
            if package.request.source_fingerprint == understanding.source_fingerprint:
                latest_result = WorkspaceLatestResult(run_id=entry.run.run_id,verdict=entry.run.verdict.value,
                    policy_epoch=entry.run.policy_epoch,created_at_us=entry.run.created_at_us,
                    summary=JUDGEMENTS[entry.run.verdict.value])
                break
        return WorkspaceCheckFacts(active_check, source_change, repair, latest_result)

    def source_drifted(self, project_id, understanding):
        try:
            return understanding.source_analysis_authorized and self.current_checks.source_inspector(project_id) != understanding.source_fingerprint
        except (JiejianError, OSError):
            return True

    def development_facts(self, project_id):
        if self.development is None:
            return None
        task = self.development.active(project_id)
        if task is None:
            return None
        view = self.development.view(project_id, task.task_id)
        delivery = view["deliveries"][0] if view["deliveries"] else None
        return WorkspaceDevelopmentFacts(task, view, delivery, view["latest_verification"])

    @contextmanager
    def preparation(self, project_id):
        with self._uow_factory() as work:
            yield PreparationReading(work, self._var_dir, work.recordings.list_for_project(project_id))


class PreparationReading:
    def __init__(self, work, var_dir, recordings):
        self._work, self._var_dir, self.recordings = work, var_dir, recordings

    def resumable(self, recording, prepared_ids):
        if (recording.state not in {RecordingState.CREATED, RecordingState.STARTING, RecordingState.RECORDING,
                RecordingState.CLEANING, RecordingState.PROCESSING, RecordingState.PENDING_REVIEW}
                or recording.subject_test_identity_id not in prepared_ids):
            return False
        try:
            require_persisted_recording_source(self._work, recording, self._var_dir)
        except JiejianError:
            return False
        return True

    def parent_for(self, action):
        work = self._work
        parent = None
        for resource in sorted(action.resources, key=lambda item: item.owner_slot_id):
            if resource.status is not PreparationStatus.SATISFIED or resource.owner_test_identity_id is None:
                continue
            binding = work.action_preparation.resource(action.action_id, action.action_revision, resource.owner_test_identity_id)
            if binding is None or binding.binding_fingerprint != resource.binding_fingerprint:
                continue
            candidate = work.recordings.get(binding.source_recording_id)
            if (candidate is None or candidate.state is not RecordingState.COMPLETED
                    or candidate.purpose is not RecordingPurpose.TARGET
                    or candidate.resource_owner_test_identity_id != resource.owner_test_identity_id):
                continue
            try:
                require_persisted_recording_source(work, candidate, self._var_dir)
            except JiejianError:
                continue
            parent = candidate
            break
        return parent
