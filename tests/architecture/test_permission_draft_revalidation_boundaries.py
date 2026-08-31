# 静态冻结权限草稿和统一变化重验的非审批、非持久化与单真源边界。

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _function_source(path: str, class_name: str, function_name: str) -> str:
    source = _source(path)
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == function_name:
                    return ast.get_source_segment(source, child) or ""
    raise AssertionError(f"missing {class_name}.{function_name}")


def test_permission_draft_has_no_approval_or_persistence_capability() -> None:
    source = _source("product/backend/workflows/permission_drafting.py")

    assert "AssistantCache" not in source
    assert "StorageUnitOfWork" not in source
    assert "approve_proposal" not in source
    assert ".confirm(" not in source
    assert ".rebind(" not in source


def test_old_permission_review_surface_is_absent() -> None:
    templates = _source("product/backend/workflows/assistant/templates.py")
    surfaces = _source("product/backend/workflows/assistant/surfaces.py")
    router = _source("product/backend/api/routers/assistant.py")

    assert "PERMISSION_REVIEW" not in templates
    assert "permission_review" not in surfaces
    assert "permission-review" not in router


def test_revalidation_plan_delegates_to_inspection() -> None:
    source = _function_source(
        "product/backend/workflows/source_changes.py",
        "SourceChangeService",
        "revalidation_plan",
    )

    assert "self.inspect_revalidation" in source
    assert "work.permission_intents" not in source
    assert "work.source_changes" not in source


def test_consumers_do_not_restore_parallel_change_judgments() -> None:
    preparation = _source("product/backend/workflows/projects/preparation.py")
    status = _source("product/backend/workflows/control.py")
    worker = _source("product/backend/composition/worker.py")
    revalidation = _source("product/backend/workflows/projects/revalidation.py")

    assert "mapping_review_required_count" not in preparation
    assert "latest.complete" not in preparation
    assert "latest_change_unverified" not in status
    assert "PermissionDraftService" not in worker
    assert "ProjectRevalidationService" not in worker
    assert "StorageUnitOfWork" not in revalidation

