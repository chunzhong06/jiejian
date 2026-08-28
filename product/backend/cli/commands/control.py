# =============================================================================
# Web V1 普通 CLI 控制面
#
# 定位
#   与 GUI 共享 ApplicationCore、产品状态、结果和历史 View 的第二控制入口。
#
# 职责
#   提供任务式命令｜选择统一产品状态｜投影 Human 与 Machine 结果
#
# 边界
#   不执行目标请求，不重算 Verdict/Evidence，不接受秘密正文或旧 Profile 路径。
# =============================================================================

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from uuid import uuid4

import typer

from product.backend.cli.bootstrap import application_scope
from product.backend.cli.presentation import (
    emit_command,
    emit_result_presentation,
    emit_status,
    fail,
    presentation_mode,
    verbose_enabled,
)
from product.backend.core.application_understanding import ActionRiskHint, CandidateDecision
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import JobState
from product.backend.core.permission_intent import PermissionIntentRelation
from product.backend.core.verification.permissions import PermissionExpectation
from product.backend.infra.runtime.jobs.models import RequestCancellation


def _dump(value: object) -> object:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, tuple):
        return [_dump(item) for item in value]
    return value


def _next_actions(status: object) -> list[dict[str, str]]:
    action = status.next_action
    return [
        {
            "action": action.action,
            "label": action.label,
            "route": action.route,
            "cli_command": action.cli_command,
        }
    ]


def status_command(
    context: typer.Context,
    project_id: str | None = typer.Option(None, "--project", help="明确选择应用"),
) -> None:
    """查看六步准备状态、唯一下一步和最近可信结果。"""

    try:
        with application_scope(context) as application:
            status = application.product_status.get(project_id)
        emit_command(
            "status",
            status,
            next_actions=_next_actions(status),
            human=lambda: emit_status(status),
        )
    except JiejianError as exc:
        fail(exc)


def app_list_command(
    context: typer.Context,
    include_archived: bool = typer.Option(
        False,
        "--include-archived",
        help="同时列出已移除应用",
    ),
) -> None:
    """列出已经正式接入的应用。"""

    try:
        with application_scope(context) as application:
            projects = application.projects.list(include_archived=include_archived)
        emit_command("app-list", [_dump(item) for item in projects])
    except JiejianError as exc:
        fail(exc)


def app_show_command(context: typer.Context, project_id: str) -> None:
    """查看应用理解事实，不触发探测或分析。"""

    try:
        with application_scope(context) as application:
            understanding = application.application_understanding.get(project_id)
        emit_command("app", understanding)
    except JiejianError as exc:
        fail(exc)


def app_connect_command(
    context: typer.Context,
    source_root: Path,
    name: str | None = typer.Option(None, "--name", help="应用显示名称"),
) -> None:
    """只读识别本地目录并建立正式应用记录。"""

    try:
        with application_scope(context) as application:
            result = application.application_understanding.connect(
                source_root,
                project_name=name,
            )
        emit_command("app-connected", result)
    except JiejianError as exc:
        fail(exc)


def app_remove_command(
    context: typer.Context,
    project_id: str,
    confirmed: bool = typer.Option(
        False,
        "--confirm",
        help="确认移除当前应用但保留源码和历史结果",
    ),
) -> None:
    """归档应用并清理当前测试身份秘密，不物理删除历史。"""

    try:
        if not confirmed:
            raise JiejianError(
                ErrorCode.STATE_OPERATOR_REQUIRED,
                "移除应用前需要使用 --confirm 明确确认",
            )
        with application_scope(context) as application:
            result = application.project_lifecycle.archive(project_id)
        emit_command("app-removed", result)
    except JiejianError as exc:
        fail(exc)


def app_discover_command(context: typer.Context, project_id: str) -> None:
    """发现应用声明的候选地址，不扩大授权目标。"""

    try:
        with application_scope(context) as application:
            result = application.application_understanding.discover_endpoints(project_id)
        emit_command("app-endpoints", result)
    except JiejianError as exc:
        fail(exc)


def app_confirm_endpoint_command(
    context: typer.Context,
    project_id: str,
    endpoint: str,
    revision: int = typer.Option(..., "--revision", min=0),
) -> None:
    """探测并确认真正要检查的本地 Web 地址。"""

    try:
        with application_scope(context) as application:
            result = application.application_understanding.confirm_endpoint(
                project_id,
                endpoint=endpoint,
                revision=revision,
            )
        emit_command("app", result)
    except JiejianError as exc:
        fail(exc)


def app_authorize_source_command(
    context: typer.Context,
    project_id: str,
    revision: int = typer.Option(..., "--revision", min=0),
) -> None:
    """明确授权只读源码分析。"""

    try:
        with application_scope(context) as application:
            result = application.application_understanding.authorize_source_analysis(
                project_id,
                revision=revision,
            )
        emit_command("app", result)
    except JiejianError as exc:
        fail(exc)


def app_analyze_command(
    context: typer.Context,
    project_id: str,
    revision: int = typer.Option(..., "--revision", min=0),
) -> None:
    """在既有只读预算内分析应用源码。"""

    try:
        with application_scope(context) as application:
            result = application.application_understanding.analyze_source(
                project_id,
                revision=revision,
            )
        emit_command("app", result)
    except JiejianError as exc:
        fail(exc)


def app_decide_role_command(
    context: typer.Context,
    project_id: str,
    candidate_id: str,
    decision: CandidateDecision,
    revision: int = typer.Option(..., "--revision", min=0),
    display_name: str | None = typer.Option(None, "--display-name"),
) -> None:
    """确认或拒绝角色候选；候选决定不生成权限规则。"""

    try:
        with application_scope(context) as application:
            result = application.application_understanding.decide_role(
                project_id,
                candidate_id,
                revision=revision,
                decision=decision,
                display_name=display_name,
            )
        emit_command("app", result)
    except JiejianError as exc:
        fail(exc)


def app_decide_action_command(
    context: typer.Context,
    project_id: str,
    candidate_id: str,
    decision: CandidateDecision,
    revision: int = typer.Option(..., "--revision", min=0),
    display_name: str | None = typer.Option(None, "--display-name"),
) -> None:
    """确认或拒绝业务动作候选；risk hint 不作为漏洞结论。"""

    try:
        with application_scope(context) as application:
            result = application.application_understanding.decide_action(
                project_id,
                candidate_id,
                revision=revision,
                decision=decision,
                display_name=display_name,
            )
        emit_command("app", result)
    except JiejianError as exc:
        fail(exc)


def app_add_role_command(
    context: typer.Context,
    project_id: str,
    display_name: str,
    revision: int = typer.Option(..., "--revision", min=0),
) -> None:
    try:
        with application_scope(context) as application:
            result = application.application_understanding.add_manual_role(
                project_id,
                revision=revision,
                display_name=display_name,
            )
        emit_command("app", result)
    except JiejianError as exc:
        fail(exc)


def app_add_action_command(
    context: typer.Context,
    project_id: str,
    display_name: str,
    revision: int = typer.Option(..., "--revision", min=0),
    risk_hint: ActionRiskHint = typer.Option(ActionRiskHint.UNKNOWN, "--risk-hint"),
) -> None:
    try:
        with application_scope(context) as application:
            result = application.application_understanding.add_manual_action(
                project_id,
                revision=revision,
                display_name=display_name,
                risk_hint=risk_hint,
            )
        emit_command("app", result)
    except JiejianError as exc:
        fail(exc)


def account_list_command(context: typer.Context, project_id: str) -> None:
    """列出应用的测试账号元数据和准备状态。"""

    try:
        with application_scope(context) as application:
            result = application.test_identities.list(project_id)
        emit_command("account-list", [_dump(item) for item in result])
    except JiejianError as exc:
        fail(exc)


def account_show_command(context: typer.Context, identity_id: str) -> None:
    try:
        with application_scope(context) as application:
            result = application.test_identities.get(identity_id)
        emit_command("account", result)
    except JiejianError as exc:
        fail(exc)


def account_create_command(
    context: typer.Context,
    project_id: str,
    role_candidate_id: str,
    label: str,
) -> None:
    """为已确认权限组创建不含秘密正文的测试账号。"""

    try:
        with application_scope(context) as application:
            result = application.test_identities.create(
                project_id,
                role_candidate_id=role_candidate_id,
                label=label,
            )
        emit_command("account", result)
    except JiejianError as exc:
        fail(exc)


def account_prepare_command(context: typer.Context, identity_id: str) -> None:
    """启动独立受控登录浏览器；秘密仍只进入 SecretStore。"""

    try:
        with application_scope(context) as application:
            result = application.identity_preparations.start(identity_id)
        emit_command("account-preparation", result)
    except JiejianError as exc:
        fail(exc)


def account_preparation_command(context: typer.Context, preparation_id: str) -> None:
    try:
        with application_scope(context) as application:
            result = application.identity_preparations.status(preparation_id)
        emit_command("account-preparation", result)
    except JiejianError as exc:
        fail(exc)


def account_confirm_command(context: typer.Context, preparation_id: str) -> None:
    try:
        with application_scope(context) as application:
            result = application.identity_preparations.confirm(preparation_id)
        emit_command("account-preparation", result)
    except JiejianError as exc:
        fail(exc)


def account_cancel_command(context: typer.Context, preparation_id: str) -> None:
    try:
        with application_scope(context) as application:
            result = application.identity_preparations.cancel(preparation_id)
        emit_command("account-preparation", result)
    except JiejianError as exc:
        fail(exc)


def account_reset_command(context: typer.Context, identity_id: str) -> None:
    try:
        with application_scope(context) as application:
            result = application.test_identities.reset(identity_id)
        emit_command("account", result)
    except JiejianError as exc:
        fail(exc)


def account_delete_command(
    context: typer.Context,
    identity_id: str,
    confirm: bool = typer.Option(False, "--confirm", help="确认删除账号和精确秘密引用"),
) -> None:
    if not confirm:
        fail(JiejianError(ErrorCode.INPUT_INVALID, "删除测试账号必须显式提供 --confirm"))
    try:
        with application_scope(context) as application:
            application.test_identities.delete(identity_id)
        emit_command("account-deleted", {"identity_id": identity_id, "deleted": True})
    except JiejianError as exc:
        fail(exc)


def flow_list_command(context: typer.Context, project_id: str) -> None:
    """列出流程录制事实；不读取浏览器原始载荷。"""

    try:
        with application_scope(context) as application:
            result = application.product_flows.list(project_id)
        emit_command("flow-list", list(result))
    except JiejianError as exc:
        fail(exc)


def flow_show_command(context: typer.Context, recording_id: str) -> None:
    try:
        with application_scope(context) as application:
            result = application.recording_lifecycle.status(recording_id)
        emit_command("flow", result)
    except JiejianError as exc:
        fail(exc)


def flow_record_command(
    context: typer.Context,
    project_id: str,
    action_candidate_id: str = typer.Option(..., "--action"),
    test_identity_id: str = typer.Option(..., "--account"),
    duration_seconds: int = typer.Option(
        60,
        "--duration-seconds",
        min=1,
        max=3_600,
        help="有界采集时长",
    ),
) -> None:
    """从当前项目、已确认动作和已准备账号完成一次受控录制。"""

    recording_id: str | None = None
    try:
        with application_scope(context, environ=os.environ) as application:
            started = application.project_recordings.submit(
                project_id,
                action_candidate_id=action_candidate_id,
                test_identity_id=test_identity_id,
                duration_seconds=duration_seconds,
                idempotency_key=f"cli-recording-{uuid4().hex}",
                headless=False,
            )
            recording_id = started.request.recording_id
            try:
                view = application.recording_runs.capture(
                    started,
                    lifecycle=application.recording_lifecycle,
                    capture_control=lambda: _wait_for_capture_stop(duration_seconds),
                    timeout_seconds=duration_seconds + 30,
                )
            finally:
                application.recording_credentials.clear(recording_id)
        emit_command(
            "flow-recorded",
            {
                "recording_id": recording_id,
                "job_id": started.result.job.job_id,
                "state": view.recording.state.value,
                "capture_phase": view.capture_phase,
                "draft_revision": view.draft.revision if view.draft else None,
            },
        )
    except JiejianError as exc:
        fail(exc)


def _wait_for_capture_stop(duration_seconds: int) -> None:
    """交互模式等待回车，Machine 与非 TTY 模式按预算自动停止。"""

    # 给 Worker 停止标记和结果发布预留时间，避免在最大预算边界竞态。
    wait_seconds = max(float(duration_seconds) - 0.5, 0.1)
    if presentation_mode() != "human" or not sys.stdin.isatty():
        time.sleep(wait_seconds)
        return
    typer.echo("在受控浏览器完成操作后回到终端确认结束（到时将自动停止）。")
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if os.name == "nt":
            import msvcrt

            if msvcrt.kbhit():
                char = msvcrt.getwch()
                if char == "\x03":
                    raise KeyboardInterrupt
                if char in {"\r", "\n"}:
                    return
        else:
            import select

            readable, _, _ = select.select([sys.stdin], [], [], 0)
            if readable:
                sys.stdin.readline()
                return
        time.sleep(0.05)


def flow_capture_start_command(context: typer.Context, recording_id: str) -> None:
    try:
        with application_scope(context) as application:
            result = application.recording_lifecycle.start_capture(recording_id)
        emit_command("flow", result)
    except JiejianError as exc:
        fail(exc)


def flow_capture_stop_command(context: typer.Context, recording_id: str) -> None:
    try:
        with application_scope(context) as application:
            result = application.recording_lifecycle.stop_capture(recording_id)
        emit_command("flow", result)
    except JiejianError as exc:
        fail(exc)


def flow_finalize_command(context: typer.Context, recording_id: str) -> None:
    try:
        with application_scope(context) as application:
            result = application.recording_lifecycle.finalize(
                recording_id,
                var_dir=application.var_dir,
                now_us=time.time_ns() // 1_000,
            )
        emit_command("flow", result)
    except JiejianError as exc:
        fail(exc)


def flow_safety_command(context: typer.Context, recording_id: str) -> None:
    try:
        with application_scope(context) as application:
            result = application.action_safety_setup.preview(recording_id)
        emit_command("flow-safety", result)
    except JiejianError as exc:
        fail(exc)


def check_permissions_command(context: typer.Context, project_id: str) -> None:
    try:
        with application_scope(context) as application:
            result = application.permission_intents.matrix(project_id)
        emit_command("check-permissions", result)
    except JiejianError as exc:
        fail(exc)


def check_set_permission_command(
    context: typer.Context,
    project_id: str,
    action_candidate_id: str,
    subject_role_candidate_id: str,
    resource_owner_role_candidate_id: str,
    relation: PermissionIntentRelation,
    expectation: PermissionExpectation | None = typer.Option(None, "--expectation"),
    actor: str = typer.Option(..., "--actor"),
) -> None:
    """确认或清除一个权限组关系单元。"""

    try:
        with application_scope(context) as application:
            result = application.permission_intents.confirm(
                project_id,
                action_candidate_id,
                subject_role_candidate_id,
                resource_owner_role_candidate_id,
                relation,
                expectation=expectation,
                actor=actor,
            )
        emit_command("check-permissions", result)
    except JiejianError as exc:
        fail(exc)


def check_preview_command(context: typer.Context, project_id: str) -> None:
    try:
        with application_scope(context) as application:
            result = application.checks.preview(project_id)
        emit_command("check-preview", result)
    except JiejianError as exc:
        fail(exc)


def check_prepare_command(
    context: typer.Context,
    project_id: str,
    actor: str = typer.Option(..., "--actor"),
) -> None:
    """调用正式编译器准备当前检查条件，并回读最新预览。"""

    try:
        with application_scope(context) as application:
            compiled = application.security_setup.compile(project_id, actor=actor)
            preview = application.checks.preview(project_id)
        emit_command(
            "check-prepared",
            {
                "preview": _dump(preview),
                "compilation": _dump(compiled),
            },
            human=lambda: _emit_check_prepared(preview, compiled),
        )
    except JiejianError as exc:
        fail(exc)


def _emit_check_prepared(preview, compiled) -> None:
    typer.echo("检查条件已经准备好" if preview.ready else "检查条件仍有缺项")
    if verbose_enabled():
        typer.echo("")
        typer.echo(f"Contract：{compiled.contract_id}@{compiled.contract_version}")
        typer.echo(f"Profile：{compiled.profile_id}")
        typer.echo(f"Hash：{compiled.profile_sha256}")


def check_cancel_command(
    context: typer.Context,
    project_id: str | None = typer.Option(None, "--project"),
) -> None:
    """取消显式项目或唯一当前项目的最新活动检查。"""

    try:
        with application_scope(context) as application:
            status = application.product_status.get(project_id)
            if status.project is None:
                raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, "当前还没有已接入应用")
            with application.uow_factory() as work:
                candidates = tuple(
                    job
                    for run in work.runs.list_for_project(status.project.project_id)
                    if (job := work.jobs.get_by_run(run.run_id)) is not None
                    and job.state
                    not in {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED}
                )
            if not candidates:
                raise JiejianError(
                    ErrorCode.JOB_NOT_FOUND,
                    "当前应用没有正在进行的检查",
                )
            job = max(candidates, key=lambda item: (item.created_at_us, item.job_id))
            result = application.job_queue.request_cancellation(
                RequestCancellation(
                    job_id=job.job_id,
                    now_us=time.time_ns() // 1_000,
                )
            )
        emit_command("check-cancelled", result)
    except JiejianError as exc:
        fail(exc)


def check_run_command(
    context: typer.Context,
    project_id: str,
    idempotency_key: str | None = typer.Option(None, "--idempotency-key"),
) -> None:
    """按当前已确认事实提交检查，不接收旧 Profile 路径。"""

    try:
        with application_scope(context) as application:
            result, request, _ = application.checks.submit(
                project_id,
                idempotency_key=idempotency_key or f"cli-{uuid4().hex}",
            )
        emit_command(
            "check-submitted",
            {
                "job": result.job.model_dump(mode="json"),
                "run": result.run.model_dump(mode="json"),
                "schema_version": request.schema_version,
            },
        )
    except JiejianError as exc:
        fail(exc)


def result_show_command(
    context: typer.Context,
    run_id: str | None = typer.Option(None, "--run"),
    project_id: str | None = typer.Option(None, "--project"),
) -> None:
    """读取同一个 ResultPresentation，包括全部 evidence_sources。"""

    try:
        with application_scope(context) as application:
            result = application.product_results.presentation(
                run_id=run_id,
                project_id=project_id,
            )
        emit_command(
            "result",
            result,
            human=lambda: emit_result_presentation(result),
        )
    except JiejianError as exc:
        fail(exc)


def result_reports_command(context: typer.Context, run_id: str) -> None:
    try:
        with application_scope(context) as application:
            result = application.reports.list(run_id)
        emit_command("result-reports", result)
    except JiejianError as exc:
        fail(exc)


def result_evidence_command(
    context: typer.Context,
    run_id: str | None = typer.Option(None, "--run"),
    project_id: str | None = typer.Option(None, "--project"),
) -> None:
    """读取显式或最近可信 Run 的已发布 Evidence 索引。"""

    try:
        with application_scope(context) as application:
            selected_run_id = run_id
            if selected_run_id is None:
                presentation = application.product_results.presentation(
                    project_id=project_id,
                )
                selected_run_id = presentation.run_id
            published = application.results.read(selected_run_id)
            evidence = tuple(
                item.model_dump(mode="json") for item in published.evidence
            )
        emit_command(
            "result-evidence",
            {
                "run_id": selected_run_id,
                "evidence": evidence,
            },
            human=lambda: _emit_evidence_summary(selected_run_id, evidence),
        )
    except JiejianError as exc:
        fail(exc)


def _emit_evidence_summary(
    run_id: str,
    evidence: tuple[dict[str, object], ...],
) -> None:
    typer.echo(f"已发布证据：{len(evidence)} 项")
    for item in evidence[:20]:
        typer.echo(
            f"- {item['evidence_id']} · {item['case_id']} · {item['artifact_path']}"
        )
    if len(evidence) > 20:
        typer.echo(f"- 其余 {len(evidence) - 20} 项请使用 --json 查看")
    if verbose_enabled():
        typer.echo("")
        typer.echo(f"Run：{run_id}")


def result_report_command(context: typer.Context, run_id: str, report_id: str) -> None:
    """读取已发布报告 JSON，并置于稳定 Machine envelope 的 data 中。"""

    try:
        with application_scope(context) as application:
            result = application.reports.read(run_id, report_id)
        emit_command("report", result)
    except JiejianError as exc:
        fail(exc)


def result_repair_command(context: typer.Context, run_id: str) -> None:
    try:
        with application_scope(context) as application:
            result = application.result_finalizer.repair(run_id)
        emit_command("result-repair", result)
    except JiejianError as exc:
        fail(exc)


def history_show_command(
    context: typer.Context,
    project_id: str | None = typer.Option(None, "--project"),
) -> None:
    """读取既有 HistoryView，不重新比较 raw Evidence。"""

    try:
        with application_scope(context) as application:
            result = application.product_results.history(project_id)
        emit_command("history", result)
    except JiejianError as exc:
        fail(exc)


def settings_show_command(context: typer.Context) -> None:
    try:
        with application_scope(context) as application:
            settings = application.llm_profiles.get_settings()
            profiles = application.llm_profiles.list()
        emit_command(
            "settings",
            {
                "settings": _dump(settings),
                "profiles": [_dump(item) for item in profiles],
            },
        )
    except JiejianError as exc:
        fail(exc)


def settings_test_command(context: typer.Context, profile_name: str) -> None:
    """显式测试已保存的模型配置；命令行不接收 API Key。"""

    try:
        with application_scope(context) as application:
            result = application.llm_profiles.test_connection(profile_name)
        emit_command("settings-profile", result)
    except JiejianError as exc:
        fail(exc)


__all__ = [name for name in globals() if name.endswith("_command")]
