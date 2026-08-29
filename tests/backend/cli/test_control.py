# Web V1 CLI 合同测试：覆盖普通命令树、Machine envelope 与同一 VarDir 单控制者。

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
    for command in ("status", "app", "account", "flow", "check", "result", "history", "settings", "system", "serve"):
        assert command in result.stdout
    for legacy in ("guide", "project ", "contract ", "recording ", "baseline ", "gate ", "cache ", "runtime ", "ci "):
        assert legacy not in result.stdout


def test_oracle_mutators_are_absent_from_cli_command_tree() -> None:
    forbidden = {
        "app": ("decide-role", "decide-action", "add-role", "add-action"),
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
    assert payload["data"]["next_action"]["action"] == "CONNECT_APPLICATION"


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


def test_check_prepare_only_compiles_then_reads_preview(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    compiled = _Model(
        contract_id="contract_demo",
        contract_version=1,
        profile_id="profile_demo",
        profile_sha256="a" * 64,
    )
    preview = _Model(ready=True, project_id="project_demo")
    application = SimpleNamespace(
        security_setup=SimpleNamespace(
            compile=lambda project_id, actor: (
                calls.append(("compile", (project_id, actor))) or compiled
            )
        ),
        checks=SimpleNamespace(
            preview=lambda project_id: (
                calls.append(("preview", project_id)) or preview
            )
        ),
    )

    @contextmanager
    def fake_scope(_context):
        yield application

    monkeypatch.setattr(control_commands, "application_scope", fake_scope)
    result = CliRunner().invoke(
        app,
        ["--json", "check", "prepare", "project_demo", "--actor", "测试用户"],
    )

    assert result.exit_code == 0
    assert calls == [
        ("compile", ("project_demo", "测试用户")),
        ("preview", "project_demo"),
    ]
    payload = json.loads(result.stdout)
    assert payload["kind"] == "check-prepared"
    assert payload["data"]["preview"]["ready"] is True


def test_authorize_source_passes_only_current_service_contract(monkeypatch) -> None:
    calls = []
    application = SimpleNamespace(
        application_understanding=SimpleNamespace(
            authorize_source_analysis=lambda project_id, revision: (
                calls.append((project_id, revision))
                or _Model(project_id=project_id, revision=revision + 1)
            )
        )
    )

    @contextmanager
    def fake_scope(_context):
        yield application

    monkeypatch.setattr(control_commands, "application_scope", fake_scope)
    result = CliRunner().invoke(
        app,
        ["--json", "app", "authorize-source", "project_demo", "--revision", "3"],
    )

    assert result.exit_code == 0
    assert calls == [("project_demo", 3)]


def test_app_list_hides_archived_by_default_and_supports_explicit_history(monkeypatch) -> None:
    calls: list[bool] = []
    application = SimpleNamespace(
        projects=SimpleNamespace(
            list=lambda *, include_archived=False: (
                calls.append(include_archived) or ()
            )
        )
    )

    @contextmanager
    def fake_scope(_context):
        yield application

    monkeypatch.setattr(control_commands, "application_scope", fake_scope)
    normal = CliRunner().invoke(app, ["--json", "app", "list"])
    historical = CliRunner().invoke(
        app,
        ["--json", "app", "list", "--include-archived"],
    )

    assert normal.exit_code == 0
    assert historical.exit_code == 0
    assert calls == [False, True]


def test_app_remove_requires_confirmation_and_uses_project_lifecycle(monkeypatch) -> None:
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
    rejected = CliRunner().invoke(app, ["--json", "app", "remove", "project_demo"])
    accepted = CliRunner().invoke(
        app,
        ["--json", "app", "remove", "project_demo", "--confirm"],
    )

    assert rejected.exit_code != 0
    assert calls == ["project_demo"]
    assert accepted.exit_code == 0
    assert json.loads(accepted.stdout)["data"]["status"] == "ARCHIVED"


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


def test_result_evidence_reads_only_published_index(monkeypatch) -> None:
    evidence = (
        _Model(
            evidence_id="evidence_demo",
            run_id="run_demo",
            case_id="case_demo",
            artifact_path="evidence/case_demo.json",
        ),
    )
    reads: list[str] = []
    application = SimpleNamespace(
        results=SimpleNamespace(
            read=lambda run_id: (
                reads.append(run_id) or SimpleNamespace(evidence=evidence)
            )
        )
    )

    @contextmanager
    def fake_scope(_context):
        yield application

    monkeypatch.setattr(control_commands, "application_scope", fake_scope)
    result = CliRunner().invoke(
        app,
        ["--json", "result", "evidence", "--run", "run_demo"],
    )

    assert result.exit_code == 0
    assert reads == ["run_demo"]
    payload = json.loads(result.stdout)
    assert payload["kind"] == "result-evidence"
    assert payload["data"]["evidence"][0]["evidence_id"] == "evidence_demo"


def test_flow_record_keeps_one_application_scope_and_clears_session(monkeypatch) -> None:
    scopes = 0
    cleared: list[str] = []
    capture_calls = []
    started = SimpleNamespace(
        request=SimpleNamespace(recording_id="rec_demo"),
        result=SimpleNamespace(job=SimpleNamespace(job_id="job_demo")),
    )
    view = SimpleNamespace(
        recording=SimpleNamespace(state=RecordingState.PENDING_REVIEW),
        capture_phase="FINISHED",
        draft=SimpleNamespace(revision=1),
    )
    application = SimpleNamespace(
        project_recordings=SimpleNamespace(submit=lambda *_args, **_kwargs: started),
        recording_runs=SimpleNamespace(
            capture=lambda *args, **kwargs: (
                capture_calls.append((args, kwargs)) or view
            )
        ),
        recording_lifecycle=object(),
        recording_credentials=SimpleNamespace(clear=cleared.append),
    )

    @contextmanager
    def fake_scope(_context, **_kwargs):
        nonlocal scopes
        scopes += 1
        yield application

    monkeypatch.setattr(control_commands, "application_scope", fake_scope)
    result = CliRunner().invoke(
        app,
        [
            "--json",
            "flow",
            "record",
            "project_demo",
            "--action",
            "action_demo",
            "--account",
            "tid_demo",
            "--duration-seconds",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert scopes == 1
    assert cleared == ["rec_demo"]
    assert len(capture_calls) == 1
    payload = json.loads(result.stdout)
    assert payload["kind"] == "flow-recorded"
    assert payload["data"]["recording_id"] == "rec_demo"


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
