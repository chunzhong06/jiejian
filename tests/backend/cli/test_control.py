# 持续验证 CLI 合同测试：覆盖普通命令树、Machine envelope 与同一 VarDir 单控制者。

from contextlib import contextmanager
import json
from types import SimpleNamespace

from typer.testing import CliRunner

from product.backend import __version__
from product.backend.cli.app import app
from product.backend.cli.commands import control as control_commands
from product.backend.core.lifecycle import JobState
from product.backend.core.recording import RecordingState
from product.backend.infra.runtime.serve_lock import ServeLock
from product.backend.workflows.control import ProductStatusService


def _empty_status():
    return ProductStatusService(
        SimpleNamespace(list=lambda: ()),
        lambda _project_id: None,
        SimpleNamespace(build=lambda _run_id: None),
    ).get()


class _Model:
    def __init__(self, **values) -> None:
        self.__dict__.update(values)

    def model_dump(self, *, mode: str):
        assert mode == "json"
        return dict(self.__dict__)


def test_top_level_help_only_exposes_web_v1_tasks_and_serve() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    for command in ("status", "application", "change", "check", "result", "history", "system", "serve"):
        assert command in result.stdout
    for legacy in ("account ", "flow ", "settings ", "guide", "project ", "contract ", "recording ", "baseline ", "gate ", "cache ", "runtime ", "ci "):
        assert legacy not in result.stdout


def test_removed_cli_aliases_and_public_runtime_flags_are_inaccessible() -> None:
    root_help = CliRunner().invoke(app, ["--help"])
    assert root_help.exit_code == 0
    for hidden_or_removed in (
        "--human",
        "--log-level",
        "--trace-id",
        "--config",
        "--var-dir",
    ):
        assert hidden_or_removed not in root_help.stdout

    removed_commands = (
        ["app", "list"],
        ["history", "show"],
        ["result", "reports", "run-demo"],
    )
    for arguments in removed_commands:
        result = CliRunner().invoke(app, arguments)
        assert result.exit_code != 0, arguments

    removed_options = (
        ["--human", "status"],
        ["--log-level", "INFO", "status"],
        ["--trace-id", "manual", "status"],
        ["--config", "settings.toml", "status"],
    )
    for arguments in removed_options:
        result = CliRunner().invoke(app, arguments)
        assert result.exit_code != 0, arguments

    serve_help = CliRunner().invoke(app, ["serve", "--help"])
    assert serve_help.exit_code == 0
    for internal in (
        "--host",
        "--port",
        "--open",
        "--frontend-dir",
        "--official-sample-root",
    ):
        assert internal not in serve_help.stdout


def test_oracle_mutators_are_absent_from_cli_command_tree() -> None:
    forbidden = {
        "application": ("decide-role", "decide-action", "add-role", "add-action"),
        "check": ("set-permission",),
    }
    for group, commands in forbidden.items():
        help_result = CliRunner().invoke(app, [group, "--help"])
        assert help_result.exit_code == 0
        for command in commands:
            assert command not in help_result.stdout
            result = CliRunner().invoke(app, [group, command])
            assert result.exit_code != 0
            assert "错误" in result.output

    for command_function in (
        "app_decide_role_command",
        "app_decide_action_command",
        "app_add_role_command",
        "app_add_action_command",
        "check_set_permission_command",
    ):
        assert not hasattr(control_commands, command_function)


def test_repair_contract_has_no_cli_command_or_alias() -> None:
    root_help = CliRunner().invoke(app, ["--help"])
    assert root_help.exit_code == 0
    assert "repair-contract" not in root_help.stdout
    for group in ("check", "result"):
        help_result = CliRunner().invoke(app, [group, "--help"])
        assert help_result.exit_code == 0
        assert "repair" not in help_result.stdout
        assert CliRunner().invoke(app, [group, "repair"]).exit_code != 0


def test_version_uses_the_single_product_version_source() -> None:
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout == f"{__version__}\n"
    assert result.stderr == ""


def test_status_machine_output_is_one_stable_stdout_object(monkeypatch) -> None:
    application = SimpleNamespace(product_status=SimpleNamespace(get=lambda _project: _empty_status()))

    @contextmanager
    def fake_scope(_context):
        yield application

    monkeypatch.setattr(control_commands, "application_scope", fake_scope)
    result = CliRunner().invoke(app, ["--json", "status"])

    assert result.exit_code == 0
    assert result.stderr == ""
    assert result.stdout.count("\n") == 1
    payload = json.loads(result.stdout)
    assert list(payload) == ["data", "kind", "next_actions", "schema_version", "status", "warnings"]
    assert payload["schema_version"] == "1"
    assert payload["kind"] == "status"
    assert payload["status"] == "ok"
    assert payload["data"]["attention_items"][0]["key"] == "connect-application"
    assert payload["next_actions"][0]["route"] == "/application"


def test_result_machine_output_keeps_shared_presentation_diagnosis(monkeypatch) -> None:
    sources = [
        {"observer_type": "DATABASE", "label": "数据库状态", "role": "KEY", "status": "FOUND", "evidence_refs": ["evidence-db"]},
        {"observer_type": "AUDIT_LOG", "label": "审计日志", "role": "SUPPORTING", "status": "UNAVAILABLE", "evidence_refs": []},
    ]

    class Presentation:
        def model_dump(self, *, mode: str):
            assert mode == "json"
            return {
                "run_id": "run_demo",
                "verdict": "BLOCK",
                "issues": [
                    {
                        "evidence_sources": sources,
                        "diagnosis": {
                            "breakpoint_type": "AUTHORIZATION_LATE",
                            "precision": "EXACT",
                            "minimal_witness": [],
                            "confirmed_impacts": [],
                        },
                    }
                ],
            }

    application = SimpleNamespace(
        product_results=SimpleNamespace(presentation=lambda **_kwargs: Presentation())
    )

    @contextmanager
    def fake_scope(_context):
        yield application

    monkeypatch.setattr(control_commands, "application_scope", fake_scope)
    result = CliRunner().invoke(app, ["--json", "result", "show", "--run", "run_demo"])

    assert result.exit_code == 0
    assert result.stderr == ""
    payload = json.loads(result.stdout)
    assert payload["kind"] == "result"
    assert payload["data"]["issues"][0]["evidence_sources"] == sources
    assert payload["data"]["issues"][0]["diagnosis"]["breakpoint_type"] == "AUTHORIZATION_LATE"
    assert payload["data"]["issues"][0]["diagnosis"]["precision"] == "EXACT"


def test_check_prepare_uses_change_aware_workflow(monkeypatch) -> None:
    calls: list[tuple[str, object, object]] = []
    preview = _Model(ready=True, project_id="project_demo")
    application = SimpleNamespace(
        checks=SimpleNamespace(
            prepare=lambda project_id, *, change_id: (
                calls.append(("prepare", project_id, change_id)) or preview
            )
        ),
    )

    @contextmanager
    def fake_scope(_context):
        yield application

    monkeypatch.setattr(control_commands, "application_scope", fake_scope)
    result = CliRunner().invoke(
        app,
        ["--json", "check", "prepare", "project_demo", "--change", f"chg_{'1' * 32}"],
    )

    assert result.exit_code == 0
    assert calls == [("prepare", "project_demo", f"chg_{'1' * 32}")]
    payload = json.loads(result.stdout)
    assert payload["kind"] == "check-prepared"
    assert payload["data"]["preview"]["ready"] is True


def test_application_list_only_uses_current_product_catalog(monkeypatch) -> None:
    calls: list[str] = []
    application = SimpleNamespace(
        projects=SimpleNamespace(
            list=lambda: (
                calls.append("list") or ()
            )
        )
    )

    @contextmanager
    def fake_scope(_context):
        yield application

    monkeypatch.setattr(control_commands, "application_scope", fake_scope)
    normal = CliRunner().invoke(app, ["--json", "application", "list"])
    historical = CliRunner().invoke(app, ["application", "list", "--include-archived"])

    assert normal.exit_code == 0
    assert historical.exit_code != 0
    assert calls == ["list"]


def test_application_show_uses_bounded_product_summary(monkeypatch) -> None:
    status = SimpleNamespace(
        project=SimpleNamespace(
            project_id="project_demo",
            name="演示应用",
            status=SimpleNamespace(value="READY"),
        ),
        readiness=SimpleNamespace(
            endpoint_status="CONFIRMED",
            source_analysis_status="COMPLETED",
            confirmed_role_count=2,
            confirmed_action_count=3,
            completed_flow_available=True,
            active_contract_available=True,
            current_scope_runnable=True,
        ),
        attention_items=(SimpleNamespace(
            label="查看当前安全基线",
            description="查看真实业务后果。",
            route="/results",
        ),),
    )
    application = SimpleNamespace(product_status=SimpleNamespace(get=lambda _project: status))

    @contextmanager
    def fake_scope(_context):
        yield application

    monkeypatch.setattr(control_commands, "application_scope", fake_scope)
    result = CliRunner().invoke(
        app,
        ["--json", "application", "show", "project_demo"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)["data"]
    assert payload["name"] == "演示应用"
    assert payload["confirmed_business_facts"] == {
        "business_action_count": 3,
        "permission_group_count": 2,
    }
    assert payload["preparation"]["check_ready"] is True
    encoded = result.stdout
    for forbidden in (
        "source_root",
        "source_fingerprint",
        "candidate",
        "line_number",
        "detector",
        "revision",
    ):
        assert forbidden not in encoded


def test_change_list_is_bounded_and_check_run_freezes_selected_change(monkeypatch) -> None:
    change_id = f"chg_{'4' * 32}"
    calls: list[tuple[str, object]] = []
    change = _Model(
        change_id=change_id,
        project_id="project_demo",
        reason="Agent 增加导出能力",
        summary="需要重新确认 1 条权限规则。",
        added_count=1,
        modified_count=0,
        removed_count=0,
    )
    application = SimpleNamespace(
        source_changes=SimpleNamespace(
            list_views=lambda project_id, *, limit: (
                calls.append(("list", (project_id, limit))) or (change,)
            )
        ),
        checks=SimpleNamespace(
            submit=lambda project_id, *, idempotency_key, change_id: (
                calls.append(("run", (project_id, change_id)))
                or (
                    SimpleNamespace(
                        job=_Model(job_id="job_demo"),
                        run=_Model(run_id="run_demo"),
                    ),
                    SimpleNamespace(schema_version="1"),
                    None,
                )
            )
        ),
    )

    @contextmanager
    def fake_scope(_context):
        yield application

    monkeypatch.setattr(control_commands, "application_scope", fake_scope)
    listed = CliRunner().invoke(
        app,
        ["--json", "change", "list", "project_demo", "--limit", "12"],
    )
    run = CliRunner().invoke(
        app,
        ["--json", "check", "run", "project_demo", "--change", change_id],
    )

    assert listed.exit_code == run.exit_code == 0
    assert calls == [
        ("list", ("project_demo", 12)),
        ("run", ("project_demo", change_id)),
    ]


def test_application_remove_requires_confirmation_and_uses_project_lifecycle(monkeypatch) -> None:
    calls: list[str] = []
    application = SimpleNamespace(
        project_lifecycle=SimpleNamespace(
            archive=lambda project_id: (
                calls.append(project_id)
                or _Model(project_id=project_id, status="ARCHIVED")
            )
        )
    )

    @contextmanager
    def fake_scope(_context):
        yield application

    monkeypatch.setattr(control_commands, "application_scope", fake_scope)
    rejected = CliRunner().invoke(app, ["--json", "application", "remove", "project_demo"])
    accepted = CliRunner().invoke(
        app,
        ["--json", "application", "remove", "project_demo", "--confirm"],
    )

    assert rejected.exit_code != 0
    assert calls == ["project_demo"]
    assert accepted.exit_code == 0
    assert json.loads(accepted.stdout)["data"]["status"] == "ARCHIVED"


def test_result_report_uses_default_or_explicit_published_report(monkeypatch) -> None:
    reads: list[tuple[str, str]] = []
    application = SimpleNamespace(
        reports=SimpleNamespace(
            list=lambda run_id: [
                {"report_id": "report-default"},
                {"report_id": "report-other"},
            ],
            read=lambda run_id, report_id: (
                reads.append((run_id, report_id))
                or {"report_id": report_id}
            ),
        )
    )

    @contextmanager
    def fake_scope(_context):
        yield application

    monkeypatch.setattr(control_commands, "application_scope", fake_scope)
    default = CliRunner().invoke(
        app,
        ["--json", "result", "report", "--run", "run-demo"],
    )
    specified = CliRunner().invoke(
        app,
        [
            "--json",
            "result",
            "report",
            "--run",
            "run-demo",
            "--report",
            "report-other",
        ],
    )

    assert default.exit_code == specified.exit_code == 0
    assert reads == [
        ("run-demo", "report-default"),
        ("run-demo", "report-other"),
    ]


def test_check_cancel_resolves_latest_nonterminal_run_job(monkeypatch) -> None:
    old = SimpleNamespace(
        job_id=f"job_{'1' * 32}",
        state=JobState.RUNNING,
        created_at_us=1,
    )
    latest = SimpleNamespace(
        job_id=f"job_{'2' * 32}",
        state=JobState.PENDING,
        created_at_us=2,
    )
    terminal = SimpleNamespace(
        job_id=f"job_{'3' * 32}",
        state=JobState.SUCCEEDED,
        created_at_us=3,
    )
    jobs = {"run_old": old, "run_latest": latest, "run_done": terminal}

    @contextmanager
    def fake_uow():
        yield SimpleNamespace(
            runs=SimpleNamespace(
                list_for_project=lambda _project_id: tuple(
                    SimpleNamespace(run_id=run_id) for run_id in jobs
                )
            ),
            jobs=SimpleNamespace(get_by_run=lambda run_id: jobs[run_id]),
        )

    cancellations = []
    application = SimpleNamespace(
        product_status=SimpleNamespace(
            get=lambda _project_id: SimpleNamespace(
                project=SimpleNamespace(project_id="project_demo")
            )
        ),
        uow_factory=fake_uow,
        job_queue=SimpleNamespace(
            request_cancellation=lambda request: (
                cancellations.append(request) or _Model(job_id=request.job_id)
            )
        ),
    )

    @contextmanager
    def fake_scope(_context):
        yield application

    monkeypatch.setattr(control_commands, "application_scope", fake_scope)
    result = CliRunner().invoke(app, ["--json", "check", "cancel"])

    assert result.exit_code == 0
    assert [item.job_id for item in cancellations] == [f"job_{'2' * 32}"]
    assert json.loads(result.stdout)["kind"] == "check-cancelled"


def test_gui_lock_rejects_cli_before_application_core_is_created(tmp_path, monkeypatch) -> None:
    var_dir = tmp_path / "var"
    owner = ServeLock.acquire(var_dir)
    monkeypatch.setattr(
        "product.backend.workflows.context.ApplicationCore",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("不应创建第二个 ApplicationCore")),
    )
    try:
        result = CliRunner().invoke(
            app,
            ["--var-dir", str(var_dir), "--json", "status"],
        )
    finally:
        owner.release()

    assert result.exit_code == 4
    assert result.stderr == ""
    payload = json.loads(result.stdout)
    assert payload["kind"] == "error"
    assert payload["error"]["error_code"] == "WORKSPACE_ALREADY_CONTROLLED"
    assert payload["error"]["trace_id"].startswith("cli-")
    assert payload["error"]["recovery"]
