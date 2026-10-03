# 按原阶段读取工作区事实，再调用纯选择与展示；不持久化页面状态或另算安全结论。
from __future__ import annotations
from product.backend.workflows.workspace.models import WorkspaceConnectionView, WorkspaceProjectView, WorkspaceView
from product.backend.workflows.workspace.reading import WorkspaceReader, WorkspaceCheckReaders
from product.backend.workflows.workspace.presentation import boundary_views, endpoint_status, source_status, area_views, journey_view, development_view
from product.backend.workflows.workspace.tasks import boundary_task, allow_control_task, PreparationTaskSelection, current_check_task, development_task, CheckPreviewRequired


class WorkspaceService:
    """协调当前事实读取与唯一主任务选择；各阶段保持原先按条件读取的顺序。"""

    def __init__(self, uow_factory, business_boundaries, *, preparation, var_dir=None,
                 current_checks: WorkspaceCheckReaders | None = None, development=None):
        self._business_boundaries, self._preparation = business_boundaries, preparation
        self._reader = WorkspaceReader(uow_factory, var_dir=var_dir, current_checks=current_checks, development=development)

    def validate_connections(self):
        self._reader.validate_connections()

    def get(self, project_id: str) -> WorkspaceView:
        project, understanding = self._reader.project(project_id)
        boundary = self._business_boundaries.view(project_id)
        pending = self._business_boundaries.proposals(project_id, pending_only=True).proposals
        connection = WorkspaceConnectionView(endpoint_status=endpoint_status(understanding), source_analysis_status=source_status(understanding))
        actors, actions, boundary_attention = boundary_views(boundary, pending)
        primary_task = boundary_task(understanding, boundary, pending)
        preparation = self._preparation.get(project_id)
        if primary_task is None:
            primary_task = self._preparation_task(boundary, preparation, understanding)
        latest_result, source_change, repair, active_check = None, None, None, None
        ports = self._reader.current_checks
        if ports is not None:
            facts = self._reader.checks(project_id, boundary, understanding)
            active_check, source_change, repair, latest_result = facts.active_check, facts.source_change, facts.repair, facts.latest_result
            if primary_task is None:
                task = next((item for item in repair.tasks if item.task_reference == repair.primary_task_reference), None)
                drifted = self._reader.source_drifted(project_id, understanding)
                primary_task = current_check_task(task, drifted, latest_result)
                if isinstance(primary_task, CheckPreviewRequired):
                    primary_task = current_check_task(task, drifted, latest_result, ports.checks.preview(project_id).can_execute)
        development = None
        development_facts = self._reader.development_facts(project_id)
        if development_facts is not None:
            development = development_view(development_facts)
            selected = development_task(primary_task, development_facts, boundary_attention, active_check)
            if isinstance(selected, CheckPreviewRequired):
                preview = ports.checks.preview(project_id, change_id=selected.change_id)
                selected = development_task(primary_task, development_facts, boundary_attention, active_check, preview)
            primary_task = selected
        return WorkspaceView(project=WorkspaceProjectView(project_id=project.project_id, name=project.name,
            status=project.status, target_type=project.target_type), connection=connection, actors=actors, actions=actions,
            primary_task=primary_task, areas=area_views(boundary_attention, preparation.preparation_complete),
            latest_result=latest_result, source_change=source_change, repair=repair, active_check=active_check,
            development=development, journey=journey_view(connection, boundary_attention, preparation.preparation_complete,
                primary_task, latest_result, source_change, active_check))

    def _preparation_task(self, boundary, preparation, understanding):
        selected = allow_control_task(preparation)
        if selected is not None:
            return selected
        candidates = []
        with self._reader.preparation(preparation.project_id) as reading:
            for action in sorted(preparation.actions, key=lambda item: item.action_id):
                selection = PreparationTaskSelection(boundary, action, understanding, reading.recordings)
                for recording in selection.current_recordings:
                    if reading.resumable(recording, selection.prepared_ids):
                        selection.resume_recording(recording)
                selection.prepare_missing()
                selection.complete_materials(reading.parent_for(action))
                candidates.extend(selection.candidates)
        return min(candidates, key=lambda item: item[0])[1] if candidates else None


__all__ = ["WorkspaceService"]
