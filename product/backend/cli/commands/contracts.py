# Contract CLI 命令组
# 适配建约、审阅、Diff 与 Drift 命令，实际治理逻辑复用 ContractWorkbench。

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import typer

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.verification.permissions import PermissionContract
from product.backend.cli.bootstrap import application_scope
from product.backend.cli.presentation import emit_json, fail


def contract_validate_command(path: Path) -> None:
    """离线校验独立 Contract Schema。"""

    try:
        contract = PermissionContract.model_validate_json(path.read_bytes(), strict=True)
        emit_json(
            {
                "schema_version": "1",
                "kind": "contract",
                "valid": True,
                "contract_id": contract.contract_id,
                "version": contract.version,
            }
        )
    except JiejianError as exc:
        fail(exc)


@contextmanager
def _workbench_scope(
    context: typer.Context, profile_path: Path
) -> Iterator[tuple[object, str]]:
    with application_scope(context) as application:
        record, _ = application.projects.register(profile_path)
        yield application, record.project_id


def _workbench_emit(context: typer.Context, profile_path: Path, action) -> None:
    try:
        with _workbench_scope(context, profile_path) as (application, project_id):
            emit_json(action(application, project_id))
    except JiejianError as exc:
        fail(exc)


def contract_workspace_command(context: typer.Context, profile_path: Path) -> None:
    """登记当前 ExecutionProfile，输出契约治理工作台快照。"""

    _workbench_emit(
        context,
        profile_path,
        lambda application, project_id: application.contract_workbench.snapshot(
            project_id
        ).model_dump(mode="json"),
    )


def contract_requirement_add_command(
    context: typer.Context,
    profile_path: Path,
    text: str = typer.Option(..., "--text"),
    tag: list[str] | None = typer.Option(
        None, "--tag", help="安全标签；可重复指定"
    ),
    actor: str = typer.Option("local-user", "--actor"),
) -> None:
    """创建一个受控需求文本记录。"""

    _workbench_emit(
        context,
        profile_path,
        lambda application, project_id: application.contract_workbench.create_requirement(
            project_id, text=text, security_tags=tuple(tag or ()), actor=actor
        ).model_dump(mode="json"),
    )


def contract_derive_command(
    context: typer.Context,
    profile_path: Path,
    requirement: list[str] | None = typer.Option(
        None, "--requirement", help="需求 ID；可重复指定"
    ),
    actor: str = typer.Option("local-user", "--actor"),
) -> None:
    """从选定需求派生候选。"""

    _workbench_emit(
        context,
        profile_path,
        lambda application, project_id: application.contract_workbench.derive_candidates(
            project_id,
            requirement_ids=tuple(requirement or ()),
            actor=actor,
        ).model_dump(mode="json"),
    )


def contract_draft_command(
    context: typer.Context,
    profile_path: Path,
    contract_id: str,
    snapshot_path: Path = typer.Option(..., "--snapshot", help="完整权限契约（PermissionContract）JSON"),
    actor: str = typer.Option("local-user", "--actor"),
) -> None:
    """用明确候选创建 Contract DRAFT。"""

    _workbench_emit(
        context,
        profile_path,
        lambda application, project_id: application.contract_workbench.create_draft(
            project_id,
            contract_id,
            snapshot=_read_contract(snapshot_path),
            actor=actor,
        ).model_dump(mode="json"),
    )


def contract_revise_command(
    context: typer.Context,
    profile_path: Path,
    contract_id: str,
    snapshot_path: Path = typer.Option(..., "--snapshot", help="下一版本完整权限契约（PermissionContract）JSON"),
    actor: str = typer.Option("local-user", "--actor"),
) -> None:
    """用明确候选修订 ACTIVE Contract。"""

    _workbench_emit(
        context,
        profile_path,
        lambda application, project_id: application.contract_workbench.revise_active(
            project_id,
            contract_id,
            snapshot=_read_contract(snapshot_path),
            actor=actor,
        ).model_dump(mode="json"),
    )


def contract_transition_command(
    context: typer.Context,
    profile_path: Path,
    contract_id: str,
    version: int,
    action: str = typer.Argument(..., help="动作值：submit（提交）、reject（拒绝）或 activate（激活）"),
    actor: str = typer.Option("local-user", "--actor"),
) -> None:
    """执行 Contract Version 的 submit、reject 或 activate 状态动作。"""

    def transition(application: ApplicationCore, project_id: str) -> dict:
        if action == "submit":
            result = application.contract_workbench.submit_review(
                project_id, contract_id, version, actor=actor
            )
        elif action == "reject":
            result = application.contract_workbench.reject_review(
                project_id, contract_id, version, actor=actor
            )
        elif action == "activate":
            result = application.contract_workbench.activate_review(
                project_id, contract_id, version, actor=actor
            )
        else:
            raise JiejianError(
                ErrorCode.INPUT_INVALID,
                "状态动作必须是 submit、reject 或 activate",
            )
        return result.model_dump(mode="json")

    _workbench_emit(context, profile_path, transition)


def contract_assessment_command(
    context: typer.Context, profile_path: Path, contract_id: str, version: int
) -> None:
    """输出 Contract Version 的确定性 assessment。"""

    _workbench_emit(
        context,
        profile_path,
        lambda application, project_id: application.contract_workbench.assessment(
            project_id, contract_id, version
        ).model_dump(mode="json"),
    )


def contract_diff_command(
    context: typer.Context,
    profile_path: Path,
    contract_id: str,
    version: int,
    from_version: int = typer.Option(..., "--from-version", min=1),
) -> None:
    """输出 Contract Version 与指定版本的确定性差分。"""

    _workbench_emit(
        context,
        profile_path,
        lambda application, project_id: application.contract_workbench.diff(
            project_id, contract_id, version, from_version
        ).model_dump(mode="json"),
    )


def contract_drift_command(
    context: typer.Context, profile_path: Path, contract_id: str, version: int
) -> None:
    """输出当前需求、候选和观察能力的 DriftReport。"""

    _workbench_emit(
        context,
        profile_path,
        lambda application, project_id: application.contract_workbench.drift(
            project_id, contract_id, version
        ).model_dump(mode="json"),
    )


def contract_history_command(context: typer.Context, run_id: str) -> None:
    """从当前 var-dir 解析 Run 执行时的 Contract 快照。"""

    try:
        with application_scope(context) as application:
            emit_json(application.contract_workbench.history(run_id).model_dump(mode="json"))
    except JiejianError as exc:
        fail(exc)


def _read_contract(path: Path) -> PermissionContract:
    try:
        return PermissionContract.model_validate_json(path.read_bytes(), strict=True)
    except (OSError, ValueError):
        raise JiejianError(ErrorCode.CONTRACT_REFERENCE_INVALID, "完整 PermissionContract 不可读取") from None
