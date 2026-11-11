# 按原阶段读取工作区事实，再调用纯选择与展示；不持久化页面状态或另算安全结论。
from __future__ import annotations
from product.backend.application.reading import projection_read
from product.backend.application.workspace.models import WorkspaceConnectionView, WorkspaceProjectView, WorkspaceView, PreparationWorkView, PreparationWorkAction
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.application.workspace.reading import WorkspaceReader, WorkspaceCheckReaders
from product.backend.application.workspace.presentation import boundary_views, endpoint_status, source_status, area_views, journey_view, development_view
from product.backend.application.workspace.tasks import boundary_task, current_check_task, development_task, CheckPreviewRequired
from product.backend.application.workspace.preparation import preparation_task


class WorkspaceService:
    """协调当前事实读取与唯一主任务选择；各阶段保持原先按条件读取的顺序。"""

    def __init__(self, uow_factory, business_boundaries, *, preparation, var_dir=None,
                 current_checks: WorkspaceCheckReaders | None = None, development=None):
        self._business_boundaries, self._preparation = business_boundaries, preparation
        self._reader = WorkspaceReader(uow_factory, var_dir=var_dir, current_checks=current_checks, development=development)

    def validate_connections(self):
        self._reader.validate_connections()

    @projection_read
    def get(self, project_id: str, *, prepared=None) -> WorkspaceView:
        project, understanding = self._reader.project(project_id)
        boundary = self._business_boundaries.view(project_id)
        pending = self._business_boundaries.proposals(project_id, pending_only=True).proposals
        connection = WorkspaceConnectionView(endpoint_status=endpoint_status(understanding), source_analysis_status=source_status(understanding))
        actors, actions, boundary_attention = boundary_views(boundary, pending)
        primary_task = boundary_task(understanding, boundary, pending)
        # 同请求上层已经读取准备事实时复用；不存到实例上，也不跨请求复用。
        preparation = prepared if prepared is not None and prepared.project_id == project_id else self._preparation.get(project_id)
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

    @projection_read
    def preparation_work(self, project_id: str, action_ids: tuple[str, ...]) -> PreparationWorkView:
        """只组织显式范围中的准备任务，失效对象拒绝；读取不触发目标或持久化另一份进度。"""
        if not action_ids or len(action_ids) > 256 or len(set(action_ids)) != len(action_ids):
            raise JiejianError(ErrorCode.INPUT_INVALID, "请提供本次检查的明确业务操作范围。")
        _, understanding = self._reader.project(project_id)
        boundary = self._business_boundaries.view(project_id)
        preparation = self._preparation.get(project_id)
        selected = tuple(item for item in preparation.actions if item.action_id in action_ids)
        if {item.action_id for item in selected} != set(action_ids):
            raise JiejianError(ErrorCode.RECORD_NOT_FOUND, "本次范围中的业务操作已变化，请返回原检查重新核对。")
        scoped = preparation.model_copy(update={"actions": selected})
        return PreparationWorkView(project_id=project_id,
            actions=tuple(PreparationWorkAction(action_id=item.action_id, label=item.display_name,
                action_revision=item.action_revision,
                preparation_complete=item.preparation_complete) for item in selected),
            primary_task=self._preparation_task(boundary, scoped, understanding),
            preparation_complete=all(item.preparation_complete for item in selected))

    def _preparation_task(self, boundary, preparation, understanding):
        with self._reader.preparation(preparation.project_id) as reading:
            return preparation_task(boundary, preparation, understanding, reading)


__all__ = ["WorkspaceService"]
