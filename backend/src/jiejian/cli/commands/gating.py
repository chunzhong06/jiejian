# =============================================================================
# 阶段 7.2 Baseline/Gate CLI 适配器
#
# 新命令使用 GateResult 的 PASS=0、BLOCK=1、ERROR=2；旧 ci 命令不经过此处。
# =============================================================================

from __future__ import annotations

import typer

from ...application.context import ApplicationContext
from ...verification.gating import GateDecision, GatePolicy
from ..bootstrap import runtime_settings
from ..presentation import emit_json, fail
from ...errors import JiejianError


def baseline_accept_command(
    context: typer.Context,
    run_id: str = typer.Argument(..., help="已发布且已完成的 Run ID"),
    actor: str = typer.Option(..., "--actor"),
    reason: str = typer.Option(..., "--reason"),
) -> None:
    application = None
    try:
        settings = runtime_settings(context)
        application = ApplicationContext(settings.var_dir)
        emit_json(application.gating.accept_baseline(run_id, actor=actor, reason=reason))
    except JiejianError as exc:
        fail(exc)
    finally:
        if application is not None:
            application.close()


def gate_evaluate_command(
    context: typer.Context,
    baseline_id: str = typer.Argument(...),
    run_id: str = typer.Argument(...),
    minimum_severity: str = typer.Option("low", "--minimum-severity"),
) -> None:
    application = None
    decision = None
    try:
        settings = runtime_settings(context)
        application = ApplicationContext(settings.var_dir)
        result = application.gating.evaluate(
            baseline_id,
            run_id,
            policy=GatePolicy(minimum_severity=minimum_severity),
        )
        emit_json(result)
        decision = result["decision"]
    except JiejianError as exc:
        fail(exc)
    finally:
        if application is not None:
            application.close()
    raise typer.Exit(code={GateDecision.PASS.value: 0, GateDecision.BLOCK.value: 1, GateDecision.ERROR.value: 2}[decision])


def gate_result_command(
    context: typer.Context,
    gate_result_id: str = typer.Argument(...),
) -> None:
    application = None
    try:
        settings = runtime_settings(context)
        application = ApplicationContext(settings.var_dir)
        emit_json(application.gating.get_gate_result(gate_result_id))
    except JiejianError as exc:
        fail(exc)
    finally:
        if application is not None:
            application.close()
