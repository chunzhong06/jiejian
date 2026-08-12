from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from jiejian.api import create_app


def test_workbench_service_derivation_is_atomic_and_idempotent(tmp_path: Path) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    with TestClient(app):
        context = app.state.context
        project, _ = context.projects.register(Path("samples/fixed_apps/ownership/project.yaml").resolve())
        malformed = context.contract_workbench.create_requirement(
            project.project_id,
            text="uncovered natural language",
            security_tags=(),
            actor="analyst",
        )
        blocked = context.contract_workbench.derive_candidates(
            project.project_id,
            requirement_ids=(malformed.requirement_id,),
            include_flow=False,
            actor="analyst",
        )
        assert blocked.persisted_candidates == ()
        with context.uow_factory() as work:
            assert work.contract_candidates.list_for_project(project.project_id) == ()

        requirement = context.contract_workbench.create_requirement(
            project.project_id,
            text="rule id=foreign-read kind=foreign_read observers=http severity=high",
            security_tags=("ownership",),
            actor="analyst",
        )
        first = context.contract_workbench.derive_candidates(
            project.project_id,
            requirement_ids=(requirement.requirement_id,),
            include_flow=False,
            actor="analyst",
        )
        second = context.contract_workbench.derive_candidates(
            project.project_id,
            requirement_ids=(requirement.requirement_id,),
            include_flow=False,
            actor="analyst",
        )
        assert first.persisted_candidates == second.persisted_candidates
        with context.uow_factory() as work:
            assert len(work.contract_candidates.list_for_project(project.project_id)) == 1
