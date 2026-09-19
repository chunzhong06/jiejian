# 验证 当前组合根以稳定业务边界为真源，并隔离延期旧能力。

from __future__ import annotations

import ast
from pathlib import Path

from product.backend.core.business_boundary import (
    ActionImplementationBinding,
    ActorImplementationBinding,
    BusinessRevisionState,
)
from product.backend.core.permission_intent import PermissionIntentRevision
from product.backend.core.test_identity import TestIdentity as IdentityModel
from product.backend.infra.storage.business_boundaries import (
    ActionImplementationBindingRow,
    ActorImplementationBindingRow,
)
from product.backend.workflows.business_boundaries import (
    BoundaryMaintenanceActionItem,
    BoundaryMaintenanceActorItem,
    BoundaryMaintenanceCommand,
    BoundaryMaintenancePermissionItem,
)


ROOT = Path(__file__).resolve().parents[2]


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _imported_names(relative: str) -> set[str]:
    tree = ast.parse(_source(relative))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.update(alias.name for alias in node.names)
            if node.module is not None:
                names.add(node.module)
    return names


def test_permission_and_identity_models_reference_only_stable_business_ids() -> None:
    permission_fields = set(PermissionIntentRevision.model_fields)
    assert {
        "subject_actor_id",
        "subject_actor_revision",
        "business_action_id",
        "action_revision",
        "resource_owner_actor_id",
        "resource_owner_actor_revision",
        "protected_effect_ids",
    } <= permission_fields
    assert not {
        "subject_role_name",
        "resource_owner_role_name",
        "role_candidate_id",
        "action_candidate_id",
        "effect_definitions",
    } & permission_fields
    assert {"actor_id", "actor_revision"} <= set(IdentityModel.model_fields)
    assert "role_candidate_id" not in IdentityModel.model_fields


def test_domain_models_do_not_import_discovery_candidates() -> None:
    for relative in (
        "product/backend/core/business_boundary.py",
        "product/backend/core/permission_intent.py",
    ):
        imports = _imported_names(relative)
        assert "product.backend.core.application_understanding" not in imports
        assert not {"RoleCandidate", "ActionCandidate"} & imports


def test_binding_persists_provenance_not_live_status() -> None:
    for model in (ActorImplementationBinding, ActionImplementationBinding):
        fields = set(model.model_fields)
        assert {
            "basis_version",
            "candidate_snapshots",
            "source_proposal_id",
            "confirmed_at_us",
            "binding_fingerprint",
        } <= fields
        assert not {"status", "reason_codes"} & fields
    for row in (ActorImplementationBindingRow, ActionImplementationBindingRow):
        columns = set(row.__table__.columns.keys())
        assert {
            "basis_version",
            "candidate_snapshots_json",
            "source_proposal_id",
            "confirmed_at_us",
        } <= columns
        assert not {"status", "reason_codes_json"} & columns
    assert {item.value for item in BusinessRevisionState} == {"ACTIVE", "RETIRED"}
    assert "inspect_actor_binding" in _source(
        "product/backend/workflows/business_boundaries/service.py"
    )
    assert "inspect_action_binding" in _source(
        "product/backend/workflows/business_boundaries/service.py"
    )
    assert "SUPERSEDED" not in _source(
        "product/frontend/src/api/businessBoundaries.ts"
    )


def test_proposal_repository_has_no_mutation_entrypoint() -> None:
    source = _source("product/backend/infra/storage/business_boundaries.py")
    assert "def add_proposal(" in source
    assert "def add_decision(" in source
    assert "def replace_proposal(" not in source
    assert "def update_proposal(" not in source


def test_current_api_registers_business_boundary_and_workspace_surfaces() -> None:
    tree = ast.parse(_source("product/backend/api/app.py"))
    routers = {
        ast.unparse(node.args[0].func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "include_router" and node.args and isinstance(node.args[0], ast.Call)
    }
    assert {
        "build_business_boundaries_router", "build_workspace_router", "build_preparation_router",
        "build_recordings_router", "build_checks_router", "build_runs_router",
        "build_results_router", "build_source_changes_router",
    } <= routers
    assert "build_permission_intents_router" not in routers


def test_maintenance_api_keeps_write_modes_server_owned() -> None:
    assert "write_mode" not in BoundaryMaintenanceCommand.model_fields
    for item_type in (
        BoundaryMaintenanceActorItem,
        BoundaryMaintenanceActionItem,
        BoundaryMaintenancePermissionItem,
    ):
        assert "write_mode" not in item_type.model_fields
    router = _source("product/backend/api/routers/business_boundaries.py")
    assert 'f"{prefix}/maintenance-draft"' in router
    assert 'f"{prefix}/maintenance-proposals"' in router
    assert "create_initial_proposal" in router
    service = _source("product/backend/workflows/business_boundaries/service.py")
    assert "write_binding: bool" in service
    assert "if plan.write_binding:" in service


def test_current_cli_does_not_register_deferred_product_commands() -> None:
    source = _source("product/backend/cli/app.py")
    assert "product.backend.cli.commands.control" not in source
    assert 'app.command("serve"' in source
    assert 'system_group.command("doctor"' in source
    for forbidden in (
        'app.command("status"',
        'app.command("history"',
        'app.add_typer(application_group',
        'app.add_typer(change_group',
        'app.add_typer(check_group',
        'app.add_typer(result_group',
    ):
        assert forbidden not in source


def test_mcp_registers_exact_tools_with_project_authorization_and_no_approval() -> None:
    source = _source("product/backend/api/mcp.py")
    expected_read = {
        "jiejian_project_list",
        "jiejian_project_show",
        "jiejian_application_understanding",
        "jiejian_business_boundary",
        "jiejian_intent_show",
        "jiejian_identity_list",
        "jiejian_system_status",
        "jiejian_change_show",
        "jiejian_check_status",
        "jiejian_result_show",
        "jiejian_repair_show",
    }
    expected = {name: "READ" for name in expected_read}
    expected.update(jiejian_change_submit="PREPARE", jiejian_check_run="EXECUTE", jiejian_check_cancel="EXECUTE")
    tools = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            if not (isinstance(decorator, ast.Call) and ast.unparse(decorator.func) == "server.tool"):
                continue
            name = next(ast.literal_eval(item.value) for item in decorator.keywords if item.arg == "name")
            assert name not in tools
            guards = [item for item in ast.walk(node) if isinstance(item, ast.Call) and ast.unparse(item.func) == "require_mcp_level"]
            assert len(guards) == 1
            tools[name] = ast.unparse(guards[0].args[2]).removeprefix("MCPAccessLevel.")
            if tools[name] != "READ":
                assert {item.arg: ast.unparse(item.value) for item in guards[0].keywords}["project_id"] == "project_id"
            called = {ast.unparse(item.func) for item in ast.walk(node) if isinstance(item, ast.Call)}
            assert not any(item.endswith((".approve_proposal", ".reject_proposal", ".add_decision")) for item in called)
    assert tools == expected
    assert "HumanApproval" not in _imported_names("product/backend/api/mcp.py")


def test_mcp_restores_only_read_without_persistent_grants() -> None:
    from product.backend.workflows.mcp_access import MCPAccessController, MCPAccessLevel
    from unittest.mock import Mock

    store = Mock()
    store.read.return_value = None
    access = MCPAccessController("http://127.0.0.1:8765/mcp", store)
    view = access.view()
    assert view.default_level is MCPAccessLevel.READ
    assert view.project_grants == ()
    store.write.assert_not_called()


def test_current_control_plane_does_not_import_or_construct_fake_worker() -> None:
    for relative in (
        "product/backend/api/app.py",
        "product/backend/api/mcp.py",
        "product/backend/api/routers/system.py",
    ):
        source = _source(relative)
        assert "CurrentWorkerSupervisor" not in source
        assert "infra.runtime.worker.current" not in source
    assert "context.worker_status()" in _source("product/backend/api/mcp.py")
    assert "LocalWorkerSupervisor(" in _source("product/backend/composition/application.py")
    assert not (
        ROOT / "product/backend/infra/runtime/worker/current.py"
    ).exists()


def test_current_workspace_replaces_status_and_dormant_frontend_state_machines() -> None:
    projects_router = _source("product/backend/api/routers/projects.py")
    workspace_router = _source("product/backend/api/routers/workspace.py")
    workspace_service = _source("product/backend/workflows/workspace/service.py")
    frontend_projects = _source("product/frontend/src/api/projects.ts")
    shell = _source("product/frontend/src/app/ControlShell.tsx")

    assert '"/api/projects/{project_id}/workspace"' in workspace_router
    assert '/api/projects/{project_id}/status' not in projects_router
    assert "ProductStatusService" not in workspace_service
    assert "ProjectReadiness" not in workspace_service
    assert "projectsApi.status" not in frontend_projects
    for forbidden in (
        "CheckResultsPage",
        "PermissionCheckPage",
        "PreparationPage",
        "PresentationMode",
        "RecordingPage",
        "TestingPage",
    ):
        assert forbidden not in shell
    for current in ("ChangesPage", "CurrentTestsPage", "CheckHistoryPage", "BusinessBoundaryPage"):
        assert current in shell
    assert "workspace?.primary_task" in shell


def test_official_recipe_is_not_an_ordinary_product_surface() -> None:
    router = _source("product/backend/api/routers/business_boundaries.py")
    service = _source("product/backend/workflows/business_boundaries/service.py")
    assert "official-recipe" not in router
    assert "def official_recipe(" not in service
    assert "def create_official_proposal(" not in service
    assert "def official_boundary_recipe(" in _source(
        "product/backend/workflows/business_boundaries/official_recipe.py"
    )


def test_maintenance_migration_extends_the_frozen_root_revision() -> None:
    versions = ROOT / "product" / "backend" / "migrations" / "versions"
    files = sorted(versions.glob("*.py"))
    assert [path.name for path in files] == [
        "0001_business_boundary_v2.py",
        "0002_business_boundary_maintenance.py",
        "0003_action_assurance_recording.py",
        "0004_action_resource_ownership.py",
        "0005_verification_loop_v3.py",
    ]
    revisions = {}
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assignments = {}
        for node in tree.body:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
            for target in targets:
                if isinstance(target, ast.Name) and target.id in {"revision", "down_revision"}:
                    assignments[target.id] = ast.literal_eval(node.value)
        revisions[assignments["revision"]] = assignments["down_revision"]
    assert revisions == {
        "0001_business_boundary_v2": None,
        "0002_business_boundary_maintenance": "0001_business_boundary_v2",
        "0003_action_assurance_recording": "0002_business_boundary_maintenance",
        "0004_action_resource_ownership": "0003_action_assurance_recording",
        "0005_verification_loop_v3": "0004_action_resource_ownership",
    }
