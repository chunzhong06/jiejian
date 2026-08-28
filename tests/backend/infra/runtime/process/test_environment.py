# 验证进程运行时中的角色化子进程环境。

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

import product.backend.infra.runtime.process.environment as process_environment_module
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.runtime.process.environment import (
    ProcessEnvironmentRole,
    minimal_process_environment,
    process_environment_failure_summary,
    spawn_python_module,
)
from tests.fixtures.runtime_environment import runtime_identity_environment


_MAIN_PROCESS_ONLY = {
    "JIEJIAN_FRONTEND_DIST",
    "JIEJIAN_NODE_EXECUTABLE",
    "JIEJIAN_PNPM_EXECUTABLE",
    "JIEJIAN_TOOLCHAIN_MANIFEST",
    "JIEJIAN_UV_EXECUTABLE",
}
_PROJECT_ROOT = Path(__file__).resolve().parents[4]


def _source(var_dir: Path) -> dict[str, str]:
    return runtime_identity_environment(
        var_dir,
        extra={
            "JIEJIAN_SERVE_LOCK_PATH": str(var_dir / "serve.lock"),
            "JIEJIAN_SERVE_OWNER_TOKEN": "serve-owner",
            "JIEJIAN_CONTROL_ORIGIN": "http://127.0.0.1:9000",
            "PLAYWRIGHT_BROWSERS_PATH": str(var_dir / "browsers"),
            "JIEJIAN_FRONTEND_DIST": str(var_dir / "runtime" / "frontend"),
            "JIEJIAN_NODE_EXECUTABLE": "node.exe",
            "JIEJIAN_PLAYWRIGHT_EXECUTABLE": "chromium.exe",
            "JIEJIAN_PNPM_EXECUTABLE": "pnpm.cmd",
            "JIEJIAN_TOOLCHAIN_MANIFEST": "toolchain.json",
            "JIEJIAN_UV_EXECUTABLE": "uv.exe",
            "WORKER_SECRET": "worker-secret",
            "RUNNER_SECRET": "runner-secret",
            "RECORDING_SECRET": "recording-secret",
            "OBSERVER_SECRET": "observer-secret",
            "SAMPLE_SECRET": "sample-secret",
            "UNRELATED_PARENT_VALUE": "must-not-cross",
            "PYTHONPATH": "must-be-removed",
        },
    )


def _capture_spawn_environment(
    monkeypatch: pytest.MonkeyPatch,
    source: dict[str, str],
    tmp_path: Path,
    *,
    role: ProcessEnvironmentRole,
    secret_names: tuple[str, ...] = (),
    extra_environment: dict[str, str] | None = None,
) -> dict[str, str]:
    captured: dict[str, Any] = {}

    class FakeProcess:
        pass

    def fake_spawn(command: list[str], **kwargs: Any) -> FakeProcess:
        captured["command"] = command
        captured.update(kwargs)
        return FakeProcess()

    monkeypatch.setattr(
        process_environment_module,
        "spawn_managed_process",
        fake_spawn,
    )
    spawn_python_module(
        source,
        "tests.fake_child",
        role=role,
        secret_names=secret_names,
        extra_environment=extra_environment,
        cwd=tmp_path,
    )
    environment = captured["env"]
    assert isinstance(environment, dict)
    return environment


def test_minimal_environment_is_scoped_by_fixed_role(tmp_path: Path) -> None:
    source = _source(tmp_path / "var")

    worker = minimal_process_environment(
        source,
        role=ProcessEnvironmentRole.WORKER,
        secret_names=("WORKER_SECRET",),
    )
    runner = minimal_process_environment(
        source,
        role=ProcessEnvironmentRole.RUNNER,
        secret_names=("RUNNER_SECRET",),
    )
    recording = minimal_process_environment(
        source,
        role=ProcessEnvironmentRole.RECORDING,
        secret_names=("RECORDING_SECRET",),
    )
    observer = minimal_process_environment(
        source,
        role=ProcessEnvironmentRole.OBSERVER,
        secret_names=("OBSERVER_SECRET",),
    )
    sample = minimal_process_environment(
        source,
        role=ProcessEnvironmentRole.SAMPLE,
        secret_names=("SAMPLE_SECRET",),
    )
    artifact = minimal_process_environment(
        source,
        role=ProcessEnvironmentRole.ARTIFACT_SCAN,
    )
    assert worker["JIEJIAN_SERVE_OWNER_TOKEN"] == "serve-owner"
    assert worker["JIEJIAN_CONTROL_ORIGIN"] == "http://127.0.0.1:9000"
    assert worker["WORKER_SECRET"] == "worker-secret"
    assert worker["PLAYWRIGHT_BROWSERS_PATH"] == str(
        tmp_path / "var" / "browsers"
    )
    assert runner["RUNNER_SECRET"] == "runner-secret"
    assert runner["JIEJIAN_CONTROL_ORIGIN"] == "http://127.0.0.1:9000"
    assert "JIEJIAN_SERVE_OWNER_TOKEN" not in runner
    assert recording["PLAYWRIGHT_BROWSERS_PATH"] == str(
        tmp_path / "var" / "browsers"
    )
    assert recording["RECORDING_SECRET"] == "recording-secret"
    assert observer["OBSERVER_SECRET"] == "observer-secret"
    assert sample["SAMPLE_SECRET"] == "sample-secret"
    for environment in (worker, runner, recording, observer, sample, artifact):
        assert _MAIN_PROCESS_ONLY.isdisjoint(environment)
        assert "UNRELATED_PARENT_VALUE" not in environment
        assert "PYTHONPATH" not in environment
        assert environment["PYTHONDONTWRITEBYTECODE"] == "1"
        assert environment["PYTHONNOUSERSITE"] == "1"
        assert environment["PYTHONUTF8"] == "1"
    assert "PLAYWRIGHT_BROWSERS_PATH" not in runner
    assert "PLAYWRIGHT_BROWSERS_PATH" not in observer
    assert "PLAYWRIGHT_BROWSERS_PATH" not in artifact
    assert "JIEJIAN_CONTROL_ORIGIN" not in recording
    assert "JIEJIAN_CONTROL_ORIGIN" not in observer
    assert "JIEJIAN_CONTROL_ORIGIN" not in sample
    assert "JIEJIAN_CONTROL_ORIGIN" not in artifact
    assert "WORKER_SECRET" not in runner
    assert "RUNNER_SECRET" not in recording
    assert "RECORDING_SECRET" not in observer
    assert "OBSERVER_SECRET" not in sample


def test_worker_can_forward_recording_browser_runtime(tmp_path: Path) -> None:
    source = _source(tmp_path / "var")

    worker_environment = minimal_process_environment(
        source,
        role=ProcessEnvironmentRole.WORKER,
    )
    recording_environment = minimal_process_environment(
        worker_environment,
        role=ProcessEnvironmentRole.RECORDING,
    )

    assert recording_environment["PLAYWRIGHT_BROWSERS_PATH"] == source[
        "PLAYWRIGHT_BROWSERS_PATH"
    ]
    assert "JIEJIAN_PLAYWRIGHT_EXECUTABLE" not in worker_environment
    assert "JIEJIAN_PLAYWRIGHT_EXECUTABLE" not in recording_environment


def test_portable_children_receive_release_root_without_project_root(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path / "var")
    source["JIEJIAN_RUNTIME_MODE"] = "portable"
    source["JIEJIAN_RELEASE_ROOT"] = str(tmp_path / "release")
    source["JIEJIAN_PLAYWRIGHT_EXECUTABLE"] = str(
        tmp_path / "release" / "runtime" / "playwright" / "chrome.exe"
    )
    source["PLAYWRIGHT_BROWSERS_PATH"] = str(
        tmp_path / "release" / "runtime" / "playwright"
    )
    source.pop("JIEJIAN_PROJECT_ROOT")

    child = minimal_process_environment(
        source,
        role=ProcessEnvironmentRole.WORKER,
    )

    assert child["JIEJIAN_RELEASE_ROOT"] == str(tmp_path / "release")
    assert child["JIEJIAN_PLAYWRIGHT_EXECUTABLE"] == source[
        "JIEJIAN_PLAYWRIGHT_EXECUTABLE"
    ]
    assert child["PLAYWRIGHT_BROWSERS_PATH"] == source[
        "PLAYWRIGHT_BROWSERS_PATH"
    ]
    assert "JIEJIAN_PROJECT_ROOT" not in child


def test_role_extras_are_fixed_and_cannot_override_controlled_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source(tmp_path / "var")
    recording = _capture_spawn_environment(
        monkeypatch,
        source,
        tmp_path,
        role=ProcessEnvironmentRole.RECORDING,
        secret_names=("RECORDING_SECRET",),
        extra_environment={
            "JIEJIAN_RECORDING_CANCEL_FILE": str(tmp_path / "cancel"),
            "JIEJIAN_RECORDING_ATTEMPT_DIR": str(tmp_path / "attempt"),
        },
    )
    observer = _capture_spawn_environment(
        monkeypatch,
        source,
        tmp_path,
        role=ProcessEnvironmentRole.OBSERVER,
        secret_names=("OBSERVER_SECRET",),
        extra_environment={"JIEJIAN_ATTEMPT_DIR": str(tmp_path / "observer")},
    )
    selector = _capture_spawn_environment(
        monkeypatch,
        source,
        tmp_path,
        role=ProcessEnvironmentRole.ONBOARDING_SELECTOR,
        extra_environment={"APPDATA": str(tmp_path / "appdata")},
    )

    assert recording["JIEJIAN_RECORDING_CANCEL_FILE"] == str(tmp_path / "cancel")
    assert recording["JIEJIAN_RECORDING_ATTEMPT_DIR"] == str(tmp_path / "attempt")
    assert observer["JIEJIAN_ATTEMPT_DIR"] == str(tmp_path / "observer")
    assert selector["APPDATA"] == str(tmp_path / "appdata")
    assert "JIEJIAN_SERVE_OWNER_TOKEN" not in recording
    assert "RECORDING_SECRET" not in observer

    with pytest.raises(JiejianError) as browser_override:
        spawn_python_module(
            source,
            "tests.fake_child",
            role=ProcessEnvironmentRole.RECORDING,
            extra_environment={"PLAYWRIGHT_BROWSERS_PATH": "other"},
            cwd=tmp_path,
        )
    assert browser_override.value.code == ErrorCode.RUNTIME_ENVIRONMENT_INVALID.value

    with pytest.raises(JiejianError) as worker_extra:
        spawn_python_module(
            source,
            "tests.fake_child",
            role=ProcessEnvironmentRole.WORKER,
            extra_environment={"JIEJIAN_ATTEMPT_DIR": str(tmp_path)},
            cwd=tmp_path,
        )
    assert worker_extra.value.code == ErrorCode.RUNTIME_ENVIRONMENT_INVALID.value


def test_roles_reject_missing_identity_secrets_and_invalid_names(tmp_path: Path) -> None:
    source = _source(tmp_path / "var")

    missing = dict(source)
    missing.pop("JIEJIAN_RUNTIME_FINGERPRINT")
    with pytest.raises(JiejianError) as missing_identity:
        minimal_process_environment(
            missing,
            role=ProcessEnvironmentRole.RUNNER,
        )
    assert missing_identity.value.code == ErrorCode.RUNTIME_ENVIRONMENT_INVALID.value
    assert "JIEJIAN_RUNTIME_FINGERPRINT" in missing_identity.value.to_dict()[
        "details"
    ]["missing"]
    assert process_environment_failure_summary(missing_identity.value) == {
        "reason": "COMMON_IDENTITY_MISSING",
        "missing_names": ["JIEJIAN_RUNTIME_FINGERPRINT"],
    }

    with pytest.raises(JiejianError) as artifact_secret:
        minimal_process_environment(
            source,
            role=ProcessEnvironmentRole.ARTIFACT_SCAN,
            secret_names=("ARTIFACT_SECRET",),
        )
    assert artifact_secret.value.code == ErrorCode.RUNTIME_ENVIRONMENT_INVALID.value

    with pytest.raises(JiejianError) as controlled_secret:
        minimal_process_environment(
            source,
            role=ProcessEnvironmentRole.RUNNER,
            secret_names=("jiejian_node_executable",),
        )
    assert controlled_secret.value.code == ErrorCode.RUNTIME_ENVIRONMENT_INVALID.value

    with pytest.raises(JiejianError) as invalid_secret:
        minimal_process_environment(
            source,
            role=ProcessEnvironmentRole.RUNNER,
            secret_names=("INVALID-NAME",),
        )
    assert invalid_secret.value.code == ErrorCode.RUNTIME_ENVIRONMENT_INVALID.value

    with pytest.raises(JiejianError) as invalid_role:
        minimal_process_environment(source, role="ARBITRARY")  # type: ignore[arg-type]
    assert invalid_role.value.code == ErrorCode.RUNTIME_ENVIRONMENT_INVALID.value

    with pytest.raises(JiejianError) as replaced_python:
        spawn_python_module(
            source,
            "tests.fake_child",
            role=ProcessEnvironmentRole.ARTIFACT_SCAN,
            python_executable=str(tmp_path / "other-python.exe"),
            cwd=tmp_path,
        )
    assert replaced_python.value.code == ErrorCode.RUNTIME_ENVIRONMENT_INVALID.value
    assert process_environment_failure_summary(replaced_python.value) == {
        "reason": "PYTHON_IDENTITY_MISMATCH"
    }


def test_product_python_child_calls_always_declare_a_fixed_role() -> None:
    missing: list[str] = []
    disallowed_calls: list[str] = []
    for path in (_PROJECT_ROOT / "product" / "backend").rglob("*.py"):
        source = path.read_text(encoding="utf-8-sig")
        if "allowed_extra_names" in source or "_BASE_KEYS" in source:
            disallowed_calls.append(str(path.relative_to(_PROJECT_ROOT)))
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else ""
            )
            if name not in {
                "minimal_process_environment",
                "run_python_module",
                "spawn_python_module",
            }:
                continue
            if not any(keyword.arg == "role" for keyword in node.keywords):
                missing.append(f"{path.relative_to(_PROJECT_ROOT)}:{node.lineno}")
    assert missing == []
    assert disallowed_calls == []
