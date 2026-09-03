# 验证 1.1.0 当前组合根仅暴露稳定业务边界，并隔离延期旧能力。

from __future__ import annotations

import ast
import re
from pathlib import Path

from product.backend.core.permission_intent import PermissionIntentRevision
from product.backend.core.test_identity import TestIdentity as IdentityModel


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


def test_proposal_repository_has_no_mutation_entrypoint() -> None:
    source = _source("product/backend/infra/storage/business_boundaries.py")
    assert "def add_proposal(" in source
    assert "def add_decision(" in source
    assert "def replace_proposal(" not in source
    assert "def update_proposal(" not in source


def test_current_api_registers_only_110_control_surface() -> None:
    source = _source("product/backend/api/app.py")
    assert "build_business_boundaries_router" in source
    for forbidden in (
        "build_permission_intents_router",
        "build_checks_router",
        "build_recordings_router",
        "build_runs_router",
        "build_preparation_router",
    ):
        assert forbidden not in source


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


def test_mcp_registers_exact_read_only_tool_set() -> None:
    source = _source("product/backend/api/mcp.py")
    tools = set(re.findall(r'@server\.tool\(name="([^"]+)"', source))
    assert tools == {
        "jiejian_project_list",
        "jiejian_project_show",
        "jiejian_application_understanding",
        "jiejian_business_boundary",
        "jiejian_intent_show",
        "jiejian_identity_list",
        "jiejian_system_status",
    }
    assert "HumanApproval" not in _imported_names("product/backend/api/mcp.py")


def test_current_control_plane_does_not_import_or_construct_fake_worker() -> None:
    for relative in (
        "product/backend/api/app.py",
        "product/backend/api/mcp.py",
        "product/backend/api/routers/system.py",
    ):
        source = _source(relative)
        assert "CurrentWorkerSupervisor" not in source
        assert "infra.runtime.worker.current" not in source
    assert '"worker": "unavailable"' in _source("product/backend/api/mcp.py")


def test_official_recipe_is_not_an_ordinary_product_surface() -> None:
    router = _source("product/backend/api/routers/business_boundaries.py")
    service = _source("product/backend/workflows/business_boundaries/service.py")
    assert "official-recipe" not in router
    assert "def official_recipe(" not in service
    assert "def create_official_proposal(" not in service
    assert "def official_boundary_recipe(" in _source(
        "product/backend/workflows/business_boundaries/official_recipe.py"
    )


def test_single_migration_is_the_new_root_revision() -> None:
    versions = ROOT / "product" / "backend" / "migrations" / "versions"
    files = sorted(versions.glob("*.py"))
    assert [path.name for path in files] == ["0001_business_boundary_v2.py"]
    tree = ast.parse(files[0].read_text(encoding="utf-8"))
    assignments = {
        target.id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.AnnAssign)
        and isinstance((target := node.target), ast.Name)
        and target.id in {"revision", "down_revision"}
    }
    assert assignments == {
        "revision": "0001_business_boundary_v2",
        "down_revision": None,
    }
