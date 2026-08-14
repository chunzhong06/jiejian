from __future__ import annotations

import ast
import importlib
import posixpath
import re
import tomllib
import types
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = PROJECT_ROOT / "backend" / "src" / "jiejian"
AGGREGATE_ROOTS = frozenset(
    {"jiejian.application", "jiejian.domain", "jiejian.worker"}
)
PRODUCTION_DIRECTORY_DEPTH_LIMIT = 3
SOURCE_ROOTS = (
    ("backend", PACKAGE_ROOT),
    ("frontend", PROJECT_ROOT / "frontend" / "src"),
)
FRONTEND_SOURCE_ROOT = PROJECT_ROOT / "frontend" / "src"
DEEP_PATH_EXCEPTIONS: dict[str, str] = {}
SINGLE_SUBDIRECTORY_CHAIN_EXCEPTIONS: dict[str, str] = {}
SINGLE_FILE_DIRECTORY_REVIEW: dict[str, str] = {
    "backend/src/jiejian/projects": (
        "真实项目能力边界；service.py 承担项目登记和来源完整性，独立边界保留。"
    ),
    "backend/src/jiejian/application": (
        "ApplicationContext 组合根；单文件目录承载统一资源组合边界，不展平。"
    ),
    "backend/src/jiejian/results": (
        "已发布结果读取与完整性派生视图的真实跨 API 能力边界，独立演进且不属于阶段 6 Reporting。"
    ),
    "backend/src/jiejian/worker": (
        "稳定 Worker 进程壳；内部实现已收拢至 execution，包根不重导出。"
    ),
    "frontend/src/app": (
        "组合根和用户阶段装配边界；ControlShell 负责顶层状态与路由，不展平。"
    ),
    "frontend/src/features/access": (
        "接入能力页面边界；项目注册与选择独立演进，不展平。"
    ),
    "frontend/src/features/settings": (
        "模型服务设置入口边界；profile 秘密写入与连接状态独立于六阶段业务页面。"
    ),
    "frontend/src/features/contracts": (
        "建约能力页面边界；治理工作台保持独立测试与演进，不展平。"
    ),
    "frontend/src/features/recording": (
        "录制能力页面边界；录制审阅与最终化保持独立，不展平。"
    ),
    "frontend/src/features/results": (
        "结果展示能力页面边界；报告读取与其他阶段解耦，不展平。"
    ),
    "frontend/src/features/verification": (
        "验证能力页面边界；运行观察、Finding 与 Evidence 展示独立，不展平。"
    ),
}
EXPECTED_API_ROUTE_OWNERS: dict[tuple[str, str], str] = {
    ("GET", "/health"): "system.py",
    ("GET", "/ready"): "system.py",
    ("GET", "/api/v1/system/status"): "system.py",
    ("GET", "/api/v1/llm/profiles"): "llm.py",
    ("GET", "/api/v1/llm/profiles/{profile_name}"): "llm.py",
    ("POST", "/api/v1/llm/profiles"): "llm.py",
    ("PATCH", "/api/v1/llm/profiles/{profile_name}"): "llm.py",
    ("POST", "/api/v1/llm/profiles/{profile_name}/test"): "llm.py",
    ("POST", "/api/v1/projects"): "projects.py",
    ("GET", "/api/v1/projects"): "projects.py",
    ("GET", "/api/v1/projects/{project_id}"): "projects.py",
    ("POST", "/api/v1/projects/{project_id}/revalidate"): "projects.py",
    ("GET", "/api/v1/projects/{project_id}/contracts"): "projects.py",
    ("POST", "/api/v1/projects/{project_id}/contracts/activate"): "projects.py",
    ("GET", "/api/v1/projects/{project_id}/contract-governance"): "contracts.py",
    (
        "POST",
        "/api/v1/projects/{project_id}/contract-governance/requirements",
    ): "contracts.py",
    (
        "POST",
        "/api/v1/projects/{project_id}/contract-governance/candidates/derive",
    ): "contracts.py",
    (
        "POST",
        "/api/v1/projects/{project_id}/contract-governance/candidates/llm",
    ): "contracts.py",
    (
        "POST",
        "/api/v1/projects/{project_id}/contract-governance/contracts",
    ): "contracts.py",
    (
        "POST",
        "/api/v1/projects/{project_id}/contract-governance/contracts/{contract_id}/revisions",
    ): "contracts.py",
    (
        "GET",
        "/api/v1/projects/{project_id}/contract-governance/contracts/{contract_id}/versions",
    ): "contracts.py",
    (
        "POST",
        "/api/v1/projects/{project_id}/contract-governance/contracts/{contract_id}/versions/{version}/submit",
    ): "contracts.py",
    (
        "POST",
        "/api/v1/projects/{project_id}/contract-governance/contracts/{contract_id}/versions/{version}/reject",
    ): "contracts.py",
    (
        "POST",
        "/api/v1/projects/{project_id}/contract-governance/contracts/{contract_id}/versions/{version}/activate",
    ): "contracts.py",
    (
        "GET",
        "/api/v1/projects/{project_id}/contract-governance/contracts/{contract_id}/versions/{version}/assessment",
    ): "contracts.py",
    (
        "GET",
        "/api/v1/projects/{project_id}/contract-governance/contracts/{contract_id}/versions/{version}/diff",
    ): "contracts.py",
    (
        "GET",
        "/api/v1/projects/{project_id}/contract-governance/contracts/{contract_id}/versions/{version}/drift",
    ): "contracts.py",
    ("GET", "/api/v1/runs/{run_id}/contract"): "contracts.py",
    ("POST", "/api/v1/projects/{project_id}/recordings"): "recordings.py",
    ("GET", "/api/v1/recordings/{recording_id}"): "recordings.py",
    ("GET", "/api/v1/projects/{project_id}/recordings"): "recordings.py",
    ("POST", "/api/v1/recordings/{recording_id}/review"): "recordings.py",
    ("POST", "/api/v1/recordings/{recording_id}/finalize"): "recordings.py",
    ("POST", "/api/v1/projects/{project_id}/runs"): "runs.py",
    ("GET", "/api/v1/projects/{project_id}/runs"): "runs.py",
    ("GET", "/api/v1/runs/{run_id}"): "runs.py",
    ("POST", "/api/v1/jobs/{job_id}/cancel"): "jobs.py",
    ("GET", "/api/v1/jobs/{job_id}/events"): "jobs.py",
    ("GET", "/api/v1/runs/{run_id}/report"): "results.py",
    ("GET", "/api/v1/runs/{run_id}/evidence"): "results.py",
    ("GET", "/api/v1/runs/{run_id}/findings"): "results.py",
    ("GET", "/api/v1/runs/{run_id}/evidence/{evidence_id}"): "results.py",
    ("POST", "/api/v1/onboarding/select-folder"): "onboarding.py",
    ("POST", "/api/v1/onboarding/inspect"): "onboarding.py",
    ("POST", "/api/v1/onboarding/sessions"): "onboarding.py",
    ("GET", "/api/v1/onboarding/sessions/{session_id}"): "onboarding.py",
    ("PATCH", "/api/v1/onboarding/sessions/{session_id}"): "onboarding.py",
    ("POST", "/api/v1/onboarding/sessions/{session_id}/credentials"): "onboarding.py",
    ("POST", "/api/v1/onboarding/sessions/{session_id}/quick-check"): "onboarding.py",
    ("POST", "/api/v1/onboarding/demo/start"): "onboarding.py",
    ("GET", "/api/v1/onboarding/demo"): "onboarding.py",
    ("POST", "/api/v1/onboarding/demo/stop"): "onboarding.py",
    ("POST", "/api/v2/permission-execution-profiles"): "permission_execution.py",
    ("GET", "/api/v2/projects/{project_id}/permission-execution-profiles"): "permission_execution.py",
    ("POST", "/api/v2/projects/{project_id}/runs"): "permission_execution.py",
}
EXPECTED_API_SCHEMA_OWNERS: dict[str, str] = {
    "ApiModel": "common.py",
    "ApiResponse": "common.py",
    "HealthResponse": "common.py",
    "ReadyResponse": "common.py",
    "ProjectRegisterRequest": "projects.py",
    "ContractActivateRequest": "projects.py",
    "RequirementCreateRequest": "contracts.py",
    "CandidateDeriveRequest": "contracts.py",
    "LLMCandidateRequest": "contracts.py",
    "ContractDraftRequest": "contracts.py",
    "ContractRevisionRequest": "contracts.py",
    "GovernanceActorRequest": "contracts.py",
    "RecordingCreateRequest": "recordings.py",
    "RunCreateRequest": "runs.py",
    "ReviewRequest": "recordings.py",
    "LLMProfileBase": "llm.py",
    "LLMProfileCreateRequest": "llm.py",
    "LLMProfileUpdateRequest": "llm.py",
    "LLMProfileResponse": "llm.py",
    "OnboardingInspectRequest": "onboarding.py",
    "OnboardingSessionCreateRequest": "onboarding.py",
    "OnboardingSessionUpdateRequest": "onboarding.py",
    "OnboardingCredentialsRequest": "onboarding.py",
    "OnboardingQuickCheckRequest": "onboarding.py",
    "PermissionExecutionProfileCreateRequest": "permission_execution.py",
    "PermissionExecutionRunRequest": "permission_execution.py",
}


def _python_files(directory: Path) -> tuple[Path, ...]:
    return tuple(sorted(directory.rglob("*.py")))


def _module_name(path: Path) -> str:
    relative = path.relative_to(PACKAGE_ROOT.parent).with_suffix("")
    parts = relative.parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imports(path: Path) -> set[str]:
    module = _module_name(path)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                package_parts = module.split(".")
                if path.name != "__init__.py":
                    package_parts = package_parts[:-1]
                parent_count = node.level - 1
                if parent_count:
                    package_parts = package_parts[:-parent_count]
                prefix = ".".join(package_parts)
                target = f"{prefix}.{node.module}" if node.module else prefix
            else:
                target = node.module or ""
            imports.add(target)
    return imports


def _import_from_base(path: Path, node: ast.ImportFrom) -> str:
    module = _module_name(path)
    if not node.level:
        return node.module or ""
    package_parts = module.split(".")
    if path.name != "__init__.py":
        package_parts = package_parts[:-1]
    parent_count = node.level - 1
    if parent_count:
        package_parts = package_parts[:-parent_count]
    prefix = ".".join(package_parts)
    return f"{prefix}.{node.module}" if node.module else prefix


def _resolved_import_paths(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _import_from_base(path, node)
            if base:
                imports.add(base)
            for alias in node.names:
                if alias.name != "*":
                    imports.add(f"{base}.{alias.name}" if base else alias.name)
    return imports


def _is_leaf_module(base: str, name: str) -> bool:
    if not base.startswith("jiejian."):
        return False
    module_path = PACKAGE_ROOT.joinpath(*base.split(".")[1:])
    return (
        (module_path / f"{name}.py").is_file()
        or (module_path / name / "__init__.py").is_file()
    )


def _aggregate_root_imports(path: Path) -> set[str]:
    """Return aggregate imports without mistaking leaf-module re-exports."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(
                alias.name for alias in node.names if alias.name in AGGREGATE_ROOTS
            )
        elif isinstance(node, ast.ImportFrom):
            base = _import_from_base(path, node)
            if base == "jiejian":
                imports.update(
                    f"jiejian.{alias.name}"
                    for alias in node.names
                    if f"jiejian.{alias.name}" in AGGREGATE_ROOTS
                )
            elif base in AGGREGATE_ROOTS and any(
                alias.name == "*" or not _is_leaf_module(base, alias.name)
                for alias in node.names
            ):
                imports.add(base)
    return imports


def _package_files(name: str) -> tuple[Path, ...]:
    directory = PACKAGE_ROOT / name
    return _python_files(directory) if directory.is_dir() else ()


def _dependency_hits(
    paths: tuple[Path, ...], forbidden_prefixes: tuple[str, ...]
) -> dict[str, set[str]]:
    hits: dict[str, set[str]] = {}
    for path in paths:
        dependencies = {
            dependency
            for dependency in _resolved_import_paths(path)
            if any(
                dependency == prefix or dependency.startswith(f"{prefix}.")
                for prefix in forbidden_prefixes
            )
        }
        if dependencies:
            hits[path.relative_to(PACKAGE_ROOT).as_posix()] = dependencies
    return hits


def _is_production_file(path: Path, source_kind: str) -> bool:
    if "__pycache__" in path.parts or path.suffix == ".pyc":
        return False
    if source_kind == "backend":
        return path.suffix == ".py"
    return (
        path.suffix in {".ts", ".tsx", ".js", ".jsx", ".css"}
        and ".test." not in path.name
        and ".spec." not in path.name
        and "test-setup" not in path.name
    )


def _production_files(source_root: Path, source_kind: str) -> tuple[Path, ...]:
    if not source_root.is_dir():
        return ()
    return tuple(
        sorted(
            path
            for path in source_root.rglob("*")
            if path.is_file() and _is_production_file(path, source_kind)
        )
    )


_FRONTEND_IMPORT_SOURCE = re.compile(r"(?:\bfrom\s*|\bimport\s*)[\"']([^\"']+)[\"']")


def _frontend_legacy_api_client_imports() -> dict[str, set[str]]:
    offenders: dict[str, set[str]] = {}
    for path in _production_files(FRONTEND_SOURCE_ROOT, "frontend"):
        relative = path.relative_to(FRONTEND_SOURCE_ROOT).as_posix()
        if relative == "api/client.ts" or path.suffix not in {".ts", ".tsx"}:
            continue
        parent = path.relative_to(FRONTEND_SOURCE_ROOT).parent.as_posix()
        for specifier in _FRONTEND_IMPORT_SOURCE.findall(
            path.read_text(encoding="utf-8")
        ):
            if not specifier.startswith("."):
                continue
            target = posixpath.normpath(
                posixpath.join(parent, specifier.replace("\\", "/"))
            )
            if target in {"api/client", "api/client.ts", "api/client.tsx"}:
                offenders.setdefault(relative, set()).add(specifier)
    return offenders


def _ordinary_production_files(directory: Path, source_kind: str) -> tuple[Path, ...]:
    return tuple(
        sorted(
            path
            for path in directory.iterdir()
            if path.is_file()
            and path.name != "__init__.py"
            and _is_production_file(path, source_kind)
        )
    )


def _production_files_under(directory: Path, source_kind: str) -> tuple[Path, ...]:
    return tuple(
        path
        for path in directory.rglob("*")
        if path.is_file() and _is_production_file(path, source_kind)
    )


def _source_directories(source_root: Path) -> tuple[Path, ...]:
    return (source_root, *sorted(path for path in source_root.rglob("*") if path.is_dir()))


def _source_key(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def _directory_depth(source_root: Path, path: Path) -> int:
    relative_parent = path.parent.relative_to(source_root)
    return len(relative_parent.parts)


def _unreviewed_paths(
    candidates: set[str], exceptions: dict[str, str]
) -> set[str]:
    return candidates - exceptions.keys()


def _assert_nonempty_reasons(reasons: dict[str, str]) -> None:
    assert all(isinstance(reason, str) and reason.strip() for reason in reasons.values())


def _api_router_route_owners() -> dict[tuple[str, str], str]:
    owners: dict[tuple[str, str], str] = {}
    for path in _python_files(PACKAGE_ROOT / "api" / "routers"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                if not isinstance(decorator.func, ast.Attribute):
                    continue
                if not isinstance(decorator.func.value, ast.Name):
                    continue
                if decorator.func.value.id != "router" or not decorator.args:
                    continue
                route_path = decorator.args[0]
                if not isinstance(route_path, ast.Constant) or not isinstance(
                    route_path.value, str
                ):
                    continue
                owners[(decorator.func.attr.upper(), route_path.value)] = path.name
    return owners


def _api_schema_class_definitions() -> dict[str, str]:
    definitions: dict[str, str] = {}
    schema_root = PACKAGE_ROOT / "api" / "schemas"
    for path in _python_files(schema_root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                definitions[node.name] = path.name
    return definitions


def _single_subdirectory_chain_candidates() -> set[str]:
    candidates: set[str] = set()
    for source_kind, source_root in SOURCE_ROOTS:
        candidates.update(
            _single_subdirectory_chain_candidates_for(
                source_root, source_kind, _source_key(source_root)
            )
        )
    return candidates


def _single_subdirectory_chain_candidates_for(
    source_root: Path, source_kind: str, key_prefix: str
) -> set[str]:
    candidates: set[str] = set()
    for directory in _source_directories(source_root):
        production_children = tuple(
            child
            for child in directory.iterdir()
            if child.is_dir() and _production_files_under(child, source_kind)
        )
        if not _ordinary_production_files(directory, source_kind) and len(
            production_children
        ) == 1:
            relative = directory.relative_to(source_root).as_posix()
            candidates.add(
                key_prefix if relative == "." else f"{key_prefix}/{relative}"
            )
    return candidates


def _single_file_directory_candidates() -> set[str]:
    candidates: set[str] = set()
    for _, source_root in SOURCE_ROOTS:
        source_kind = "backend" if source_root == PACKAGE_ROOT else "frontend"
        for directory in _source_directories(source_root):
            if not any(path.is_dir() for path in directory.iterdir()) and len(
                _ordinary_production_files(directory, source_kind)
            ) == 1:
                candidates.add(_source_key(directory))
    return candidates


def test_directory_depth_review_requires_explicit_reasoned_exceptions(tmp_path: Path) -> None:
    source_root = tmp_path / "src"
    deep_path = source_root / "a" / "b" / "c" / "d" / "fourth.py"
    deep_path.parent.mkdir(parents=True)
    deep_path.touch()
    relative_path = deep_path.relative_to(source_root).as_posix()

    assert _directory_depth(source_root, deep_path) == 4
    assert _unreviewed_paths({relative_path}, {}) == {relative_path}
    reasoned = {relative_path: "独立运行隔离边界"}
    assert _unreviewed_paths({relative_path}, reasoned) == set()
    _assert_nonempty_reasons(reasoned)


def test_production_directory_depth_is_reviewed() -> None:
    too_deep: set[str] = set()
    for source_kind, source_root in SOURCE_ROOTS:
        for path in _production_files(source_root, source_kind):
            if _directory_depth(source_root, path) > PRODUCTION_DIRECTORY_DEPTH_LIMIT:
                too_deep.add(_source_key(path))
    _assert_nonempty_reasons(DEEP_PATH_EXCEPTIONS)
    assert not _unreviewed_paths(too_deep, DEEP_PATH_EXCEPTIONS)


def test_contract_analysis_sources_are_exactly_three_levels_without_exception() -> None:
    sources_root = PACKAGE_ROOT / "contracts" / "analysis" / "sources"
    files = _production_files(sources_root, "backend")
    assert files
    assert all(_directory_depth(PACKAGE_ROOT, path) == 3 for path in files)
    assert not {
        _source_key(path) for path in files
    } & DEEP_PATH_EXCEPTIONS.keys()


def test_single_subdirectory_chains_are_reviewed() -> None:
    candidates = _single_subdirectory_chain_candidates()
    _assert_nonempty_reasons(SINGLE_SUBDIRECTORY_CHAIN_EXCEPTIONS)
    assert not _unreviewed_paths(candidates, SINGLE_SUBDIRECTORY_CHAIN_EXCEPTIONS)


def test_single_subdirectory_chain_review_policy_supports_exact_exceptions(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "src"
    leaf = source_root / "nested" / "leaf.py"
    leaf.parent.mkdir(parents=True)
    leaf.touch()
    candidates = _single_subdirectory_chain_candidates_for(
        source_root, "backend", "tmp/src"
    )
    assert candidates == {"tmp/src"}
    assert _unreviewed_paths(candidates, {}) == candidates
    reasoned = {"tmp/src": "独立运行隔离边界"}
    _assert_nonempty_reasons(reasoned)
    assert not _unreviewed_paths(candidates, reasoned)


def test_single_file_directories_have_explicit_review_conclusions() -> None:
    candidates = _single_file_directory_candidates()
    _assert_nonempty_reasons(SINGLE_FILE_DIRECTORY_REVIEW)
    assert candidates <= SINGLE_FILE_DIRECTORY_REVIEW.keys()
    assert set(SINGLE_FILE_DIRECTORY_REVIEW) == {
        "backend/src/jiejian/application",
        "backend/src/jiejian/projects",
        "backend/src/jiejian/results",
        "backend/src/jiejian/worker",
        "frontend/src/app",
        "frontend/src/features/access",
        "frontend/src/features/settings",
        "frontend/src/features/contracts",
        "frontend/src/features/recording",
        "frontend/src/features/results",
        "frontend/src/features/verification",
    }


def test_frontend_production_does_not_import_legacy_api_client() -> None:
    offenders = _frontend_legacy_api_client_imports()
    assert not offenders, (
        "frontend production code must import capability APIs directly; "
        f"legacy api/client imports: {offenders}"
    )


def test_domain_has_no_execution_or_infrastructure_dependencies() -> None:
    forbidden = (
        "sqlalchemy",
        "alembic",
        "httpx",
        "playwright",
        "typer",
        "jiejian.storage",
        "jiejian.runtime",
        "jiejian.verification",
    )
    dependencies = {
        dependency
        for path in _python_files(PACKAGE_ROOT / "domain")
        for dependency in _imports(path)
    }
    assert not {
        dependency
        for dependency in dependencies
        if dependency.startswith(forbidden)
    }


def test_contract_analysis_models_are_pure_over_compiled_inputs() -> None:
    path = PACKAGE_ROOT / "contracts" / "analysis" / "models.py"
    dependencies = _imports(path)
    assert not any(
        dependency.startswith(("jiejian.recording", "jiejian.application", "jiejian.storage"))
        for dependency in dependencies
    )
    source = path.read_text(encoding="utf-8")
    assert "read_bytes" not in source
    assert ".resolve(" not in source
    assert "FlowDraftReviewer" not in source


def test_contract_pure_layers_do_not_depend_on_application_or_infrastructure() -> None:
    pure_paths = (
        PACKAGE_ROOT / "contracts" / "models.py",
        PACKAGE_ROOT / "contracts" / "governance.py",
        PACKAGE_ROOT / "contracts" / "analysis" / "models.py",
        PACKAGE_ROOT / "contracts" / "analysis" / "drift.py",
        PACKAGE_ROOT / "contracts" / "llm" / "models.py",
    )
    forbidden = (
        "jiejian.application",
        "jiejian.storage",
        "fastapi",
        "sqlalchemy",
        "openai",
        "anthropic",
    )
    dependencies = {
        dependency
        for path in pure_paths
        for dependency in _imports(path)
    }
    assert not {
        dependency
        for dependency in dependencies
        if dependency.startswith(forbidden)
        and dependency != "jiejian.verification.models"
    }


def test_onboarding_discovery_is_a_read_only_leaf_and_api_uses_application_boundary() -> None:
    discovery_path = PACKAGE_ROOT / "onboarding" / "discovery.py"
    forbidden = (
        "fastapi",
        "sqlalchemy",
        "playwright",
        "jiejian.api",
        "jiejian.application",
        "jiejian.execution",
        "jiejian.storage",
        "jiejian.verification",
        "jiejian.worker",
    )
    assert not any(
        dependency == prefix or dependency.startswith(prefix + ".")
        for dependency in _imports(discovery_path)
        for prefix in forbidden
    )
    router_source = (PACKAGE_ROOT / "api" / "routers" / "onboarding.py").read_text(
        encoding="utf-8"
    )
    assert "context.onboarding" in router_source
    assert "discover_folder" not in router_source


def test_contract_analysis_algorithm_ownership_is_physical_and_explicit() -> None:
    owners = {
        "parse_requirement": PACKAGE_ROOT / "contracts" / "analysis" / "sources" / "requirement.py",
        "build_flow_candidates": PACKAGE_ROOT / "contracts" / "analysis" / "sources" / "flow.py",
        "build_openapi_candidates": PACKAGE_ROOT / "contracts" / "analysis" / "sources" / "openapi.py",
        "parse_fastapi_source_candidates": PACKAGE_ROOT / "contracts" / "analysis" / "sources" / "fastapi_ast.py",
        "merge_candidates": PACKAGE_ROOT / "contracts" / "analysis" / "merge.py",
        "assess_contract": PACKAGE_ROOT / "contracts" / "analysis" / "assessment.py",
        "diff_contract_versions": PACKAGE_ROOT / "contracts" / "analysis" / "diff.py",
    }
    models = PACKAGE_ROOT / "contracts" / "analysis" / "models.py"
    for function_name, owner in owners.items():
        tree = ast.parse(owner.read_text(encoding="utf-8"), filename=str(owner))
        definitions = [
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == function_name
        ]
        assert len(definitions) == 1, (function_name, owner)
        model_tree = ast.parse(models.read_text(encoding="utf-8"), filename=str(models))
        assert not any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == function_name
            for node in model_tree.body
        ), function_name
        imports = _resolved_import_paths(owner)
        assert not any(
            dependency.startswith(
                (
                    "jiejian.domain.contract_analysis",
                    "jiejian.domain.contract_governance",
                    "jiejian.domain.drift",
                    "jiejian.domain.llm_candidates",
                    "jiejian.application.contract_analysis",
                    "jiejian.application.contract_governance",
                    "jiejian.application.contract_workbench",
                    "jiejian.application.llm_candidates",
                )
            )
            for dependency in imports
        )


def test_protocols_do_not_depend_on_runtime_storage_cli_or_pipeline() -> None:
    forbidden = (
        "jiejian.runtime",
        "jiejian.storage",
        "jiejian.cli",
        "jiejian.verification",
    )
    dependencies = {
        dependency
        for path in _python_files(PACKAGE_ROOT / "protocols")
        for dependency in _imports(path)
    }
    assert not {
        dependency
        for dependency in dependencies
        if dependency.startswith(forbidden)
        and dependency not in {
            "jiejian.verification.models",
            "jiejian.verification.permissions",
            "jiejian.verification.permission_coverage",
        }
    }


def test_storage_does_not_depend_on_worker_verification_or_cli() -> None:
    dependencies = {
        dependency
        for path in _python_files(PACKAGE_ROOT / "storage")
        for dependency in _imports(path)
    }
    forbidden = ("jiejian.worker", "jiejian.verification", "jiejian.cli")
    assert not {
        dependency
        for dependency in dependencies
        if dependency.startswith(forbidden)
        and dependency != "jiejian.verification.models"
    }


def test_storage_orm_and_repository_aggregates_use_leaf_boundaries() -> None:
    storage_root = PACKAGE_ROOT / "storage"
    models_root = storage_root / "models"
    repositories_root = storage_root / "repositories"
    assert models_root.is_dir()
    assert repositories_root.is_dir()
    assert not (storage_root / "models.py").exists()
    assert not (storage_root / "repositories.py").exists()
    assert {
        path.name for path in models_root.glob("*.py")
    } == {
        "__init__.py",
        "base.py",
        "projects.py",
        "runs.py",
        "recordings.py",
        "contracts.py",
        "jobs.py",
        "evidence.py",
        "llm.py",
        "permission_profiles.py",
    }
    assert {
        path.name for path in repositories_root.glob("*.py")
    } == {
        "__init__.py",
        "base.py",
        "projects.py",
        "contracts.py",
        "runs.py",
        "recordings.py",
        "jobs.py",
        "evidence.py",
        "llm.py",
        "permission_profiles.py",
    }
    unit_of_work_imports = _imports(storage_root / "unit_of_work.py")
    assert "jiejian.storage.repositories" not in unit_of_work_imports
    assert {
        "jiejian.storage.repositories.contracts",
        "jiejian.storage.repositories.evidence",
        "jiejian.storage.repositories.jobs",
        "jiejian.storage.repositories.projects",
        "jiejian.storage.repositories.recordings",
        "jiejian.storage.repositories.runs",
        "jiejian.storage.repositories.llm",
        "jiejian.storage.repositories.permission_profiles",
    }.issubset(unit_of_work_imports)
    job_control_imports = _imports(storage_root / "job_control.py")
    assert "jiejian.storage.models" not in job_control_imports
    assert "jiejian.storage.repositories" not in job_control_imports
    assert {
        "jiejian.storage.models.jobs",
        "jiejian.storage.models.recordings",
        "jiejian.storage.models.runs",
        "jiejian.storage.repositories.jobs",
        "jiejian.storage.repositories.runs",
    }.issubset(job_control_imports)


def test_recording_and_execution_use_the_frozen_capability_boundaries() -> None:
    recording_root = PACKAGE_ROOT / "recording"
    execution_root = PACKAGE_ROOT / "execution"
    worker_root = PACKAGE_ROOT / "worker"
    domain_root = PACKAGE_ROOT / "domain"
    assert not (domain_root / "recording.py").exists()
    assert not (domain_root / "verification.py").exists()
    assert (recording_root / "models.py").exists()
    assert (recording_root / "job_handler.py").exists()
    assert (PACKAGE_ROOT / "verification" / "models.py").exists()
    assert (PACKAGE_ROOT / "results" / "published.py").exists()
    assert (PACKAGE_ROOT / "runtime" / "worker_manager.py").exists()
    assert (PACKAGE_ROOT / "runtime" / "serve_lock.py").exists()
    assert not (PACKAGE_ROOT / "application" / "results.py").exists()
    assert not (PACKAGE_ROOT / "application" / "worker_manager.py").exists()
    assert not (PACKAGE_ROOT / "application" / "serve_lock.py").exists()
    assert not (worker_root / "models.py").exists()
    assert not (worker_root / "events.py").exists()
    assert not (worker_root / "process_environment.py").exists()
    assert not (worker_root / "process_control.py").exists()
    assert not (worker_root / "recording.py").exists()
    assert {
        path.name for path in execution_root.glob("*.py")
    } == {
        "__init__.py",
        "attempts.py",
        "dispatch.py",
        "events.py",
        "handlers.py",
        "models.py",
        "publication.py",
        "published_artifacts.py",
        "process_control.py",
        "process_environment.py",
        "queue.py",
        "reconciliation.py",
        "recovery.py",
        "request_store.py",
        "run_handler.py",
        "requests.py",
        "submission.py",
        "permission_profile.py",
        "permission_execution.py",
        "supervisor.py",
        "targets.py",
    }
    recording_dependencies = {
        dependency
        for path in _python_files(recording_root)
        for dependency in _imports(path)
    }
    assert not {
        dependency
        for dependency in recording_dependencies
        if dependency.startswith("jiejian.worker")
    }
    execution_dependencies = {
        dependency
        for path in _python_files(execution_root)
        for dependency in _imports(path)
    }
    assert not {
        dependency
        for dependency in execution_dependencies
        if dependency.startswith(("jiejian.recording", "jiejian.recording_runner"))
    }
    process_control_imports = _imports(execution_root / "process_control.py")
    assert not {
        dependency
        for dependency in process_control_imports
        if dependency.startswith("jiejian.worker.attempts")
    }
    assert "jiejian.execution.targets" in _imports(recording_root / "job_target.py")
    runtime = PACKAGE_ROOT / "worker" / "runtime.py"
    runtime_imports = _imports(runtime)
    assert "jiejian.application.context" in runtime_imports
    runtime_source = runtime.read_text(encoding="utf-8")
    assert "build_job_handler_registry" in runtime_source
    assert ".resolve(initial_job)" in runtime_source
    assert "is_recording" not in runtime_source
    assert "RecordingJobHandler" not in runtime_source
    from jiejian.execution.models import ClaimJobV1 as ExecutionClaimJobV1
    from jiejian.recording.models import Recording
    from jiejian.worker.runtime import main as worker_runtime_main

    assert ExecutionClaimJobV1.__module__ == "jiejian.execution.models"
    assert Recording.__module__ == "jiejian.recording.models"
    assert callable(worker_runtime_main)


def test_zero_use_lifecycle_and_pipeline_leaves_are_removed() -> None:
    lifecycle = PACKAGE_ROOT / "domain" / "lifecycle.py"
    source = lifecycle.read_text(encoding="utf-8")
    assert not (PACKAGE_ROOT / "domain" / "state_machines.py").exists()
    assert not (PACKAGE_ROOT / "verification" / "pipeline.py").exists()
    for symbol in (
        "StateTransitionEvent",
        "EntityModel",
        "class Project(",
        "class Contract(",
        "class Run(",
        "class TestCase(",
        "class Job(",
    ):
        assert symbol not in source
    assert "class DomainModel" in source
    tree = ast.parse(source, filename=str(lifecycle))
    assert {
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    } == {
        "ProjectStatus",
        "ContractStatus",
        "RunLifecycle",
        "RunVerdict",
        "CaseLifecycle",
        "CaseVerdict",
        "JobState",
        "DomainModel",
    }
    assert "RunService" not in "\n".join(
        path.read_text(encoding="utf-8")
        for path in _python_files(PACKAGE_ROOT)
    )


def test_security_e2e_uses_cli_job_runner_and_preserves_isolation_assertions() -> None:
    path = PROJECT_ROOT / "tests" / "e2e" / "test_cli_security_gate.py"
    source = path.read_text(encoding="utf-8")
    assert "RunService" not in source
    assert "verification.pipeline" not in source
    assert "WorkerDispatcher" in source
    assert "runner_process_ids" in source
    assert "artifacts" in source


def test_verification_results_and_runtime_boundaries_are_leaf_owned() -> None:
    verification_models = PACKAGE_ROOT / "verification" / "models.py"
    published = PACKAGE_ROOT / "results" / "published.py"
    runtime_worker = PACKAGE_ROOT / "runtime" / "worker_manager.py"
    runtime_lock = PACKAGE_ROOT / "runtime" / "serve_lock.py"
    verification_imports = _imports(verification_models)
    assert verification_imports.issubset(
        {
            "jiejian.domain.identifiers",
            "jiejian.domain.lifecycle",
            "pydantic",
            "ipaddress",
            "re",
            "enum",
            "pathlib",
            "typing",
            "urllib.parse",
            "__future__",
        }
    )
    forbidden = (
        "jiejian.storage",
        "jiejian.execution",
        "jiejian.application",
        "jiejian.results",
        "fastapi",
        "sqlalchemy",
        "playwright",
    )
    assert not any(
        dependency.startswith(forbidden) for dependency in verification_imports
    )
    published_imports = _imports(published)
    assert not any(
        dependency.startswith(
            (
                "jiejian.verification",
                "jiejian.runner",
                "jiejian.recording",
                "jiejian.recording_runner",
                "jiejian.contracts.llm",
            )
        )
        for dependency in published_imports
    )
    for path in (runtime_worker, runtime_lock):
        imports = _imports(path)
        assert not any(
            dependency.startswith(
                ("jiejian.verification", "jiejian.recording", "jiejian.recording_runner")
            )
            for dependency in imports
        )
    all_production = _python_files(PACKAGE_ROOT)
    stale = {
        path.relative_to(PACKAGE_ROOT).as_posix(): dependency
        for path in all_production
        for dependency in _imports(path)
        if dependency in {
            "jiejian.domain.verification",
            "jiejian.application.results",
            "jiejian.application.worker_manager",
            "jiejian.application.serve_lock",
        }
    }
    assert not stale
    context = PACKAGE_ROOT / "application" / "context.py"
    api_app = PACKAGE_ROOT / "api" / "app.py"
    assert "jiejian.results.published" in _imports(context)
    assert "jiejian.runtime.worker_manager" in _imports(api_app)
    assert "context.results" in api_app.read_text(encoding="utf-8")


def test_worker_is_a_control_plane_without_cli_or_target_io_dependencies() -> None:
    worker_root = PACKAGE_ROOT / "worker"
    assert not (worker_root / "service.py").exists()
    assert {
        path.name for path in worker_root.glob("*.py")
    } == {
        "__init__.py",
        "runtime.py",
    }
    dependencies = {
        dependency
        for path in _python_files(worker_root)
        for dependency in _imports(path)
    }
    forbidden = (
        "jiejian.cli",
        "jiejian.verification",
        "httpx",
        "urllib",
        "requests",
        "playwright",
    )
    assert not {
        dependency
        for dependency in dependencies
        if dependency.startswith(forbidden)
    }


def test_target_execution_is_confined_to_explicit_adapters() -> None:
    runner_root = PACKAGE_ROOT / "runner"
    assert {path.name for path in runner_root.glob("*.py")} == {
        "__init__.py",
        "__main__.py",
        "execution.py",
        "execution_v2.py",
        "audit_log_observer.py",
        "audit_observer_process.py",
        "async_task_observer.py",
        "async_task_observer_process.py",
        "azure_blob_observer_process.py",
        "azure_queue_observer_process.py",
        "blob_observer.py",
        "observer_process.py",
        "queue_observer.py",
        "sqlite_observer.py",
    }
    cli_dependencies = {
        dependency
        for path in _python_files(PACKAGE_ROOT / "cli")
        for dependency in _imports(path)
    }
    worker_dependencies = {
        dependency
        for path in _python_files(PACKAGE_ROOT / "worker")
        for dependency in _imports(path)
    }
    assert not {
        dependency
        for dependency in worker_dependencies
        if dependency.startswith(("httpx", "jiejian.verification.http"))
    }
    assert not {
        dependency
        for dependency in cli_dependencies
        if dependency.startswith("jiejian.verification.http")
    }

    for directory_name in ("api", "worker", "results", "application"):
        dependencies = {
            dependency
            for path in _python_files(PACKAGE_ROOT / directory_name)
            for dependency in _imports(path)
        }
        assert not {
            dependency
            for dependency in dependencies
            if dependency.startswith(("jiejian.runner.sqlite_observer", "jiejian.runner.observer_process", "jiejian.runner.queue_observer", "jiejian.runner.azure_queue_observer_process", "jiejian.runner.blob_observer", "jiejian.runner.azure_blob_observer_process"))
        }
    httpx_importers = {
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in _python_files(PACKAGE_ROOT)
        if any(dependency == "httpx" for dependency in _imports(path))
    }
    assert httpx_importers == {
        "recording/transport.py",
        "verification/http.py",
        "runner/async_task_observer.py",
        "runner/queue_observer.py",
        "runner/blob_observer.py",
        "contracts/llm/adapters/httpx_transport.py",
        "cli/commands/system.py",
    }


def test_playwright_is_confined_to_recording_browser_boundary() -> None:
    playwright_importers = {
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in _python_files(PACKAGE_ROOT)
        if any(dependency.startswith("playwright") for dependency in _imports(path))
    }
    assert playwright_importers == {
        "recording/browser.py",
        "recording/events.py",
        "recording/transport.py",
        "recording/ui_capture.py",
        "recording_runner/execution.py",
        "runtime/diagnostics.py",
    }
    for protected in ("cli", "domain", "protocols", "storage", "worker"):
        path = PACKAGE_ROOT / protected
        files = (path,) if path.is_file() else _python_files(path)
        assert not any(
            dependency.startswith("playwright")
            for file in files
            for dependency in _imports(file)
        )


def test_verification_module_dependencies_are_acyclic() -> None:
    files = _python_files(PACKAGE_ROOT / "verification")
    modules = {_module_name(path) for path in files}
    graph = {
        _module_name(path): {
            dependency for dependency in _imports(path) if dependency in modules
        }
        for path in files
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(module: str) -> None:
        if module in visiting:
            raise AssertionError(f"verification dependency cycle at {module}")
        if module in visited:
            return
        visiting.add(module)
        for dependency in graph[module]:
            visit(dependency)
        visiting.remove(module)
        visited.add(module)

    for module in graph:
        visit(module)


def test_verification_v2_evaluation_is_protocol_and_adapter_free() -> None:
    path = PACKAGE_ROOT / "verification" / "evaluation_v2.py"
    imports = _imports(path)
    assert not any(
        dependency.startswith(("jiejian.protocols", "jiejian.runner", "httpx", "sqlalchemy"))
        for dependency in imports
    )


def test_old_flat_modules_are_removed_without_compatibility_wrappers() -> None:
    old_modules = {
        "artifacts.py",
        "config.py",
        "doctor.py",
        "engine.py",
        "inputs.py",
        "logging.py",
        "protocols.py",
        "safety.py",
        "services.py",
    }
    assert old_modules.isdisjoint(path.name for path in PACKAGE_ROOT.iterdir())
    assert not (PACKAGE_ROOT / "cli.py").exists()
    assert (PACKAGE_ROOT / "cli" / "__init__.py").is_file()
    assert not (PACKAGE_ROOT / "domain" / "models.py").exists()
    assert not (PACKAGE_ROOT / "domain" / "stage1.py").exists()


def test_cli_is_the_only_installed_product_command_entry() -> None:
    pyproject = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert pyproject["project"]["scripts"] == {"jiejian": "jiejian.cli:main"}
    typer_importers = {
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in _python_files(PACKAGE_ROOT)
        if any(dependency == "typer" for dependency in _imports(path))
    }
    assert typer_importers == {
        "cli/app.py",
        "cli/bootstrap.py",
        "cli/presentation.py",
        "cli/commands/system.py",
        "cli/commands/projects.py",
        "cli/commands/contracts.py",
        "cli/commands/recordings.py",
        "cli/commands/runs.py",
        "cli/commands/results.py",
    }
    assert not any(
        (PACKAGE_ROOT / name).exists()
        for name in ("main.py", "worker_main.py", "runner_main.py")
    )


def test_wheel_force_includes_preserve_single_source_resources() -> None:
    pyproject = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert pyproject["tool"]["hatch"]["build"]["targets"]["wheel"][
        "force-include"
    ] == {
        "backend/alembic.ini": "jiejian/resources/alembic.ini",
        "backend/migrations": "jiejian/resources/migrations",
        "schemas": "jiejian/resources/schemas",
    }
    assert (PROJECT_ROOT / "backend" / "alembic.ini").is_file()
    assert (PROJECT_ROOT / "backend" / "migrations").is_dir()
    assert (PROJECT_ROOT / "schemas").is_dir()
    assert not (PACKAGE_ROOT / "verification" / "pipeline.py").exists()
    assert not (PACKAGE_ROOT / "domain" / "state_machines.py").exists()


def test_minimum_comment_baseline_has_only_entry_and_detailed_sources() -> None:
    agents = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    design = (
        PROJECT_ROOT / "docs" / "01_开发规范" / "项目设计规范.md"
    ).read_text(encoding="utf-8")
    roadmap = (
        PROJECT_ROOT / "docs" / "04_开发记录" / "开发路线图.md"
    ).read_text(encoding="utf-8")
    adr_index = (
        PROJECT_ROOT / "docs" / "02_技术决策" / "README.md"
    ).read_text(encoding="utf-8")
    adr = (
        PROJECT_ROOT
        / "docs"
        / "02_技术决策"
        / "ADR-0021-最小文档真源.md"
    ).read_text(encoding="utf-8")

    assert "最低三层注释基线" in agents
    assert "最低三层注释基线" in design
    for marker in ("文件层", "类与函数层", "行内层"):
        assert marker in design
    assert "文件层" not in roadmap + adr_index + adr
    legacy_explanation_phrase = "三层" + "解释体系"
    assert legacy_explanation_phrase not in agents + design + roadmap + adr_index + adr


def test_documentation_has_only_the_current_numbered_sources() -> None:
    assert {path.name for path in (PROJECT_ROOT / "docs").iterdir()} == {
        "01_开发规范",
        "02_技术决策",
        "03_协议定义",
        "04_开发记录",
    }


def test_stage_6_to_9_design_is_versioned_and_ordered() -> None:
    design = (
        PROJECT_ROOT / "docs" / "01_开发规范" / "项目设计规范.md"
    ).read_text(encoding="utf-8")
    roadmap = (
        PROJECT_ROOT / "docs" / "04_开发记录" / "开发路线图.md"
    ).read_text(encoding="utf-8")
    adr_index = (
        PROJECT_ROOT / "docs" / "02_技术决策" / "README.md"
    ).read_text(encoding="utf-8")
    adr = (
        PROJECT_ROOT
        / "docs"
        / "02_技术决策"
        / "ADR-0023-阶段6至9能力演进与版本边界.md"
    ).read_text(encoding="utf-8")

    assert "ADR-0023" in design + roadmap + adr_index
    assert "尚未实现" in design
    stages = [roadmap.index(f"## 阶段 {number}：") for number in range(6, 10)]
    assert stages == sorted(stages)
    for marker in (
        "V2 权限意图由六个正交部分组成",
        "Observer V2",
        "FindingOccurrence",
        "RegressionBaseline",
        "GatePolicy",
        "report.json",
    ):
        assert marker in adr
    assert "不在原字段上增加可选语义" in adr


def test_new_production_code_does_not_use_aggregate_package_roots() -> None:
    """Freeze the migration rule while allowing only current, named call sites."""

    allowed_current_imports: dict[str, set[str]] = {}
    offenders: dict[str, set[str]] = {}
    for path in _python_files(PACKAGE_ROOT):
        relative = path.relative_to(PACKAGE_ROOT).as_posix()
        imports = _aggregate_root_imports(path)
        unexpected = imports - allowed_current_imports.get(relative, set())
        if unexpected:
            offenders[relative] = unexpected
    assert not offenders, (
        "new production code must import concrete capability modules; "
        f"current 5-O3 migration exceptions are explicit: {offenders}"
    )


EXPECTED_CLI_FUNCTION_OWNERS: dict[str, str] = {
    "root": "app.py",
    "main": "app.py",
    "runtime_settings": "bootstrap.py",
    "open_storage": "bootstrap.py",
    "default_frontend_dir": "bootstrap.py",
    "emit_json": "presentation.py",
    "fail": "presentation.py",
    "serve_command": "system.py",
    "_wait_for_ready": "system.py",
    "doctor_command": "system.py",
    "project_validate_command": "projects.py",
    "contract_validate_command": "contracts.py",
    "_workbench_scope": "contracts.py",
    "_workbench_emit": "contracts.py",
    "contract_workspace_command": "contracts.py",
    "contract_requirement_add_command": "contracts.py",
    "contract_derive_command": "contracts.py",
    "contract_draft_command": "contracts.py",
    "contract_revise_command": "contracts.py",
    "contract_transition_command": "contracts.py",
    "contract_assessment_command": "contracts.py",
    "contract_diff_command": "contracts.py",
    "contract_drift_command": "contracts.py",
    "contract_history_command": "contracts.py",
    "recording_start_command": "recordings.py",
    "recording_status_command": "recordings.py",
    "recording_review_command": "recordings.py",
    "recording_finalize_command": "recordings.py",
    "recording_replay_command": "recordings.py",
    "_load_recording_bindings": "recordings.py",
    "_ensure_project_record": "recordings.py",
    "run_command": "runs.py",
    "permission_run_command": "runs.py",
    "_run_persisted_job": "runs.py",
    "_persisted_request": "runs.py",
    "_required_secrets": "runs.py",
    "_published_run_result": "runs.py",
    "report_command": "results.py",
    "ci_command": "results.py",
    "_require_published_completion": "results.py",
}


def _cli_top_level_symbols() -> tuple[dict[str, str], dict[str, str]]:
    functions: dict[str, str] = {}
    classes: dict[str, str] = {}
    for path in _python_files(PACKAGE_ROOT / "cli"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions[node.name] = path.name
            elif isinstance(node, ast.ClassDef):
                classes[node.name] = path.name
    return functions, classes


def test_cli_app_is_only_composition_root_and_main() -> None:
    functions, _ = _cli_top_level_symbols()
    assert functions == EXPECTED_CLI_FUNCTION_OWNERS
    app_tree = ast.parse(
        (PACKAGE_ROOT / "cli" / "app.py").read_text(encoding="utf-8"),
        filename=str(PACKAGE_ROOT / "cli" / "app.py"),
    )
    assert {
        node.name
        for node in app_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    } == {"root", "main"}
    assert sum(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "Typer"
        for node in ast.walk(app_tree)
    ) == 4


def test_cli_package_root_exposes_only_main() -> None:
    module = importlib.import_module("jiejian.cli")
    assert module.__all__ == ["main"]
    assert {
        name
        for name, value in vars(module).items()
        if not name.startswith("__") and not isinstance(value, types.ModuleType)
    } == {"main"}
    assert module.main is importlib.import_module("jiejian.cli.app").main


def test_repository_does_not_import_private_symbols_from_cli_root() -> None:
    offenders: dict[str, set[str]] = {}
    for path in (*_python_files(PACKAGE_ROOT), *_python_files(PROJECT_ROOT / "tests")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module == "jiejian.cli"
            for alias in node.names
        }
        private = {name for name in imported if name != "main"}
        if private:
            offenders[path.relative_to(PROJECT_ROOT).as_posix()] = private
    assert not offenders, f"private CLI root imports remain: {offenders}"


def test_frontend_legacy_compatibility_files_are_removed_and_entrypoint_is_leaf() -> None:
    removed = (
        FRONTEND_SOURCE_ROOT / "App.tsx",
        FRONTEND_SOURCE_ROOT / "ContractPage.tsx",
        FRONTEND_SOURCE_ROOT / "api" / "client.ts",
        FRONTEND_SOURCE_ROOT / "compatibility.test.ts",
    )
    assert all(not path.exists() for path in removed)
    main_source = (FRONTEND_SOURCE_ROOT / "main.tsx").read_text(encoding="utf-8")
    assert "from './app/ControlShell'" in main_source
    assert "./App" not in main_source
    assert "./ContractPage" not in main_source
    assert "api/client" not in main_source


def test_cli_does_not_import_aggregate_capability_roots() -> None:
    forbidden_roots = (*AGGREGATE_ROOTS, "jiejian.recording")
    offenders = {
        path.relative_to(PACKAGE_ROOT).as_posix(): {
            dependency
            for dependency in _imports(path)
            if dependency in forbidden_roots
        }
        for path in _python_files(PACKAGE_ROOT / "cli")
        if any(dependency in forbidden_roots for dependency in _imports(path))
    }
    assert not offenders


def test_cli_internal_dependencies_are_acyclic_and_shallow() -> None:
    cli_files = _python_files(PACKAGE_ROOT / "cli")
    cli_modules = {_module_name(path) for path in cli_files}
    graph = {
        _module_name(path): {
            dependency
            for dependency in _imports(path)
            if dependency in cli_modules
        }
        for path in cli_files
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(module: str) -> None:
        if module in visiting:
            raise AssertionError(f"cli dependency cycle at {module}")
        if module in visited:
            return
        visiting.add(module)
        for dependency in graph[module]:
            visit(dependency)
        visiting.remove(module)
        visited.add(module)

    for module in graph:
        visit(module)
    assert max(_directory_depth(PACKAGE_ROOT, path) for path in cli_files) == 2


def test_cli_default_frontend_dir_keeps_the_previous_repository_target() -> None:
    from jiejian.cli.bootstrap import default_frontend_dir

    old_target = (
        PROJECT_ROOT / "backend" / "src" / "jiejian" / "cli.py"
    ).resolve().parents[3] / "frontend" / "dist"
    assert default_frontend_dir() == old_target


def test_api_app_only_assembles_routers_and_lifecycle() -> None:
    path = PACKAGE_ROOT / "api" / "app.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    assert {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    } == {"create_app"}
    http_route_decorators = {
        "delete",
        "get",
        "head",
        "patch",
        "post",
        "put",
        "options",
        "trace",
    }
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "app"
        and node.func.attr in http_route_decorators
        for node in ast.walk(tree)
    )
    assert sum(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "include_router"
        for node in ast.walk(tree)
    ) == 10


def test_api_routes_are_defined_by_the_frozen_routers() -> None:
    assert _api_router_route_owners() == EXPECTED_API_ROUTE_OWNERS


def test_api_schema_classes_are_defined_in_leaf_modules_without_root_reexports() -> None:
    assert _api_schema_class_definitions() == EXPECTED_API_SCHEMA_OWNERS
    init_path = PACKAGE_ROOT / "api" / "schemas" / "__init__.py"
    tree = ast.parse(init_path.read_text(encoding="utf-8"), filename=str(init_path))
    assert not any(isinstance(node, ast.ClassDef) for node in tree.body)
    assert not any(isinstance(node, ast.ImportFrom) for node in tree.body)
    assert not any(
        isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "__all__"
            for target in node.targets
        )
        for node in tree.body
    )


def test_api_internal_dependencies_are_acyclic() -> None:
    api_files = _python_files(PACKAGE_ROOT / "api")
    api_modules = {_module_name(path) for path in api_files}
    graph = {
        _module_name(path): {
            dependency
            for dependency in _imports(path)
            if dependency in api_modules
        }
        for path in api_files
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(module: str) -> None:
        if module in visiting:
            raise AssertionError(f"api dependency cycle at {module}")
        if module in visited:
            return
        visiting.add(module)
        for dependency in graph[module]:
            visit(dependency)
        visiting.remove(module)
        visited.add(module)

    for module in graph:
        visit(module)


def test_old_contract_facades_are_removed_and_no_imports_remain() -> None:
    legacy_modules = {
        "jiejian.domain.contract_analysis",
        "jiejian.domain.contract_governance",
        "jiejian.domain.drift",
        "jiejian.domain.llm_candidates",
        "jiejian.application.contract_analysis",
        "jiejian.application.contract_governance",
        "jiejian.application.contract_workbench",
        "jiejian.application.llm_candidates",
    }
    removed_paths = {
        "domain/contract_analysis.py",
        "domain/contract_governance.py",
        "domain/drift.py",
        "domain/llm_candidates.py",
        "application/services.py",
        "application/contract_analysis.py",
        "application/contract_governance.py",
        "application/contract_workbench.py",
        "application/llm_candidates.py",
    }
    assert all(not (PACKAGE_ROOT / path).exists() for path in removed_paths)
    offenders: dict[str, set[str]] = {}
    for path in _python_files(PACKAGE_ROOT):
        relative = path.relative_to(PACKAGE_ROOT).as_posix()
        unexpected = {
            dependency
            for dependency in _imports(path)
            if dependency in legacy_modules or dependency.startswith(tuple(f"{module}." for module in legacy_modules))
        }
        if unexpected:
            offenders[relative] = unexpected
    assert not offenders


def test_package_roots_are_empty_aggregates_and_recording_is_lazy() -> None:
    for module_name in (
        "jiejian.application",
        "jiejian.domain",
        "jiejian.worker",
        "jiejian.recording",
        "jiejian.api.schemas",
        "jiejian.runner",
        "jiejian.recording_runner",
    ):
        module = importlib.import_module(module_name)
        assert not hasattr(module, "__all__")
        assert not any(
            name
            for name, value in vars(module).items()
            if not name.startswith("__") and not isinstance(value, types.ModuleType)
        )
    import sys

    recording_init = PACKAGE_ROOT / "recording" / "__init__.py"
    tree = ast.parse(recording_init.read_text(encoding="utf-8"), filename=str(recording_init))
    assert not any(
        isinstance(node, (ast.Import, ast.ImportFrom))
        and any(
            (alias.name if isinstance(node, ast.Import) else node.module or "").startswith(
                "playwright"
            )
            for alias in node.names
        )
        for node in tree.body
    )


def test_storage_and_formal_entrypoints_use_leaf_modules() -> None:
    assert "jiejian.api.schemas" not in _imports(PACKAGE_ROOT / "api" / "app.py")
    for path in _python_files(PACKAGE_ROOT / "api" / "routers"):
        assert not any(
            dependency == "jiejian.api.schemas"
            for dependency in _imports(path)
        )
    for path in _python_files(PACKAGE_ROOT / "projects"):
        source = path.read_text(encoding="utf-8")
        assert "execution_request_compat" not in source
        assert "bind_execution_request_compat" not in source
        assert "def execution_request" not in source


def test_current_package_root_compatibility_exports_are_not_reintroduced() -> None:
    for module_name in (
        "jiejian.application",
        "jiejian.domain",
        "jiejian.worker",
        "jiejian.recording",
        "jiejian.api.schemas",
        "jiejian.runner",
        "jiejian.recording_runner",
    ):
        module = importlib.import_module(module_name)
        assert not hasattr(module, "__all__")
        assert not hasattr(module, "__getattr__")


def test_application_context_registers_run_and_recording_handlers(tmp_path: Path) -> None:
    from jiejian.application.context import ApplicationContext
    from jiejian.execution.targets import JobTargetType

    context = ApplicationContext(tmp_path / "var")
    try:
        assert set(context.job_targets._handlers) == {
            JobTargetType.RUN,
            JobTargetType.RECORDING,
        }
        registry = context.build_job_handler_registry("architecture-test", {})
        assert set(registry._factories) == {
            JobTargetType.RUN,
            JobTargetType.RECORDING,
        }
    finally:
        context.close()


def test_worker_runtime_and_execution_core_boundaries_remain_stable() -> None:
    runtime = PACKAGE_ROOT / "worker" / "runtime.py"
    dispatch = PACKAGE_ROOT / "execution" / "dispatch.py"
    execution = PACKAGE_ROOT / "verification" / "execution.py"
    assert runtime.is_file()
    assert "python -m jiejian.worker.runtime" in runtime.read_text(encoding="utf-8")
    assert "jiejian.worker.runtime" in dispatch.read_text(encoding="utf-8")
    execution_imports = _imports(execution)
    assert not any(
        dependency.startswith(("jiejian.recording", "jiejian.recording_runner"))
        for dependency in execution_imports
    )


def test_capability_dependencies_follow_frozen_stage5_o3_directions() -> None:
    projects_contracts = _dependency_hits(
        _package_files("projects"), ("jiejian.contracts",)
    )
    assert not projects_contracts

    execution_paths = _package_files("execution")
    verification_execution = PACKAGE_ROOT / "verification" / "execution.py"
    if verification_execution.is_file():
        execution_paths = (*execution_paths, verification_execution)
    execution_recording = _dependency_hits(
        execution_paths, ("jiejian.recording", "jiejian.recording_runner")
    )
    assert not execution_recording

    capability_context_hits: dict[str, set[str]] = {}
    for capability in (
        "projects",
        "contracts",
        "recording",
        "verification",
        "execution",
        "results",
        "runtime",
    ):
        capability_context_hits.update(
            _dependency_hits(
                _package_files(capability), ("jiejian.application.context",)
            )
        )
    assert not capability_context_hits


def test_application_context_is_the_composition_root_without_workbench_cycle() -> None:
    application_files = _python_files(PACKAGE_ROOT / "application")
    application_modules = {_module_name(path) for path in application_files}
    graph = {
        _module_name(path): {
            dependency
            for dependency in _imports(path)
            if dependency in application_modules
        }
        for path in application_files
    }
    assert not (PACKAGE_ROOT / "application" / "services.py").exists()
    assert "jiejian.application.context" not in _imports(PACKAGE_ROOT / "contracts" / "workbench.py")
    assert "jiejian.contracts.workbench" in _imports(PACKAGE_ROOT / "application" / "context.py")
    assert "jiejian.application.projects" not in graph
    assert {
        "jiejian.projects.service",
        "jiejian.execution.requests",
    }.issubset(_imports(PACKAGE_ROOT / "application" / "context.py"))

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(module: str) -> None:
        if module in visiting:
            raise AssertionError(f"application dependency cycle at {module}")
        if module in visited:
            return
        visiting.add(module)
        for dependency in graph[module]:
            visit(dependency)
        visiting.remove(module)
        visited.add(module)

    for module in graph:
        visit(module)


def test_projects_service_does_not_access_contract_capability_or_repository() -> None:
    project_files = _package_files("projects")
    assert not _dependency_hits(project_files, ("jiejian.contracts",))
    assert all(
        "contract_versions" not in path.read_text(encoding="utf-8")
        for path in project_files
    )
