"""路径型输入适配器；执行规则全部委托给快照核心。"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from uuid import uuid4

from ..domain.verification import RunResult
from .execution import SnapshotRunExecutor, VerificationSnapshot
from .inputs import ProjectBundle, load_project_bundle


def snapshot_from_bundle(bundle: ProjectBundle) -> VerificationSnapshot:
    """移除 YAML 路径，形成可供共享执行核心使用的内容快照。"""

    project = bundle.project
    return VerificationSnapshot(
        project_id=project.id,
        project_name=project.name,
        target=project.target,
        identities=project.identities,
        resources=project.resources,
        flow=bundle.flow,
        contract=bundle.contract,
        owner_observer_enabled=project.owner_observer_enabled,
        mutation_seed=project.mutation_seed,
    )


class RunService:
    """阶段 1 路径输入适配器；测试和兼容调用不直接承载执行规则。"""

    def __init__(
        self,
        var_dir: Path,
        *,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self.var_dir = var_dir.resolve()
        self.environ = os.environ if environ is None else environ

    def run(
        self,
        project_path: Path,
        *,
        contract_path: Path | None = None,
    ) -> RunResult:
        bundle = load_project_bundle(project_path, contract_path=contract_path)
        snapshot = snapshot_from_bundle(bundle)
        run_id = f"run_{uuid4().hex}"
        artifact_dir = self.var_dir / "projects" / snapshot.project_id / "runs" / run_id
        return SnapshotRunExecutor(environ=self.environ).run(
            snapshot,
            run_id=run_id,
            artifact_dir=artifact_dir,
        )
