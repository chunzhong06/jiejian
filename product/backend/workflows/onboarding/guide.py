# =============================================================================
# Guide Query Service
#
# 定位
#   CLI 引导模式的只读状态投影。
#
# 职责
#   从项目、Execution Profile 和 Run Repository 形成当前引导快照。
#
# 边界
#   不保存 Guide 状态，不提交事务，不重新实现业务规则。
# =============================================================================

from __future__ import annotations

from collections.abc import Callable


class GuideQueryService:
    """只读组合现有项目、Profile 和运行记录。"""

    def __init__(self, projects, execution, uow_factory: Callable[..., object]) -> None:
        self._projects = projects
        self._execution = execution
        self._uow_factory = uow_factory

    def snapshot(self) -> dict[str, object]:
        """生成不带独立持久状态的引导快照。"""

        projects = self._projects.list()
        items: list[dict[str, object]] = []
        recent_runs = []
        for project in projects:
            profiles = self._execution.list(project.project_id)
            with self._uow_factory() as work:
                runs = work.runs.list_for_project(project.project_id)
            recent_runs.extend((project, run) for run in runs)
            items.append(
                {
                    "project": project,
                    "profiles": profiles,
                    "permission_rules_ready": (
                        project.governed_contract_id is not None
                        and project.governed_contract_version is not None
                    ),
                }
            )
        recent_runs.sort(key=lambda item: item[1].created_at_us, reverse=True)
        return {
            "projects": tuple(items),
            "recent_runs": tuple(recent_runs),
        }
