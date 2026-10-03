# 验证受控启动副本、真实进程回执和旧代码不能代表新交付的边界。
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from product.backend.infra.runtime.process import ProcessEnvironmentRole, spawn_python_module
from product.backend.infra.runtime.process.controlled.artifact import create_runtime_artifact, read_runtime_manifest, verify_runtime_artifact
from product.backend.infra.runtime.process.tree import release_process_tree, terminate_process_tree
from product.protocols.runtime.runtime_identity import RuntimeFile, RuntimeLaunchReceipt, receipt_matches
from tests.fixtures.runtime.runtime_environment import runtime_identity_environment


def _fixture(tmp_path: Path):
    source = tmp_path / "workspace"
    source.mkdir()
    data = b"import sys\nfrom pathlib import Path\nPath(sys.argv[1]).write_text('original', encoding='utf-8')\n"
    (source / "server.py").write_bytes(data)
    files = (RuntimeFile(relative_path="server.py", sha256=hashlib.sha256(data).hexdigest(), size=len(data)),)
    environment = runtime_identity_environment(tmp_path / "var")
    root, manifest = create_runtime_artifact(source, tmp_path / "var" / "artifacts", files=files,
        entry_module="server", interpreter_fingerprint=environment["JIEJIAN_RUNTIME_FINGERPRINT"])
    return source, root, manifest, environment


def test_frozen_launch_runs_original_code_after_workspace_changes(tmp_path: Path):
    source, root, manifest, environment = _fixture(tmp_path)
    (source / "server.py").write_text("raise RuntimeError('new unlaunched code')", encoding="utf-8")
    output = tmp_path / "result.txt"
    process = spawn_python_module(environment, "product.backend.infra.runtime.process.controlled.target",
        "--manifest", str(root / "launch.json"), "--", str(output),
        role=ProcessEnvironmentRole.SAMPLE, cwd=root / "source",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        _, stderr = process.communicate(timeout=15)
        assert process.returncode == 0, stderr.decode("utf-8", errors="replace")
        receipt = RuntimeLaunchReceipt.model_validate_json((root / "started.json").read_bytes())
        assert receipt_matches(manifest, receipt, owned_process_id=process.pid)
        assert not receipt_matches(manifest, receipt, owned_process_id=process.pid + 1)
        assert output.read_text(encoding="utf-8") == "original"
        assert read_runtime_manifest(root / "launch.json") == manifest
    finally:
        if process.poll() is None:
            terminate_process_tree(process, 3)
        release_process_tree(process)


@pytest.mark.parametrize("change", ["edit", "delete", "extra"])
def test_artifact_drift_is_rejected(tmp_path: Path, change: str):
    _, root, manifest, _ = _fixture(tmp_path)
    target = root / "source" / "server.py"
    if change == "edit":
        target.write_text("changed", encoding="utf-8")
    elif change == "delete":
        target.unlink()
    else:
        (root / "source" / "hidden.py").write_text("extra", encoding="utf-8")
    with pytest.raises(ValueError):
        verify_runtime_artifact(root / "source", manifest)


@pytest.mark.parametrize("path", ["../server.py", "/server.py", "C:/server.py", "con.py", "file:stream", "trailing./a", "x\\y"])
def test_noncanonical_runtime_paths_rejected(path: str):
    with pytest.raises(ValidationError):
        RuntimeFile(relative_path=path, sha256="0" * 64, size=0)


def test_wrong_instance_and_changed_manifest_cannot_reuse_receipt(tmp_path: Path):
    _, _, manifest, _ = _fixture(tmp_path)
    from product.protocols.runtime.runtime_identity import runtime_manifest_fingerprint
    receipt = RuntimeLaunchReceipt(instance_id=manifest.instance_id, manifest_fingerprint=runtime_manifest_fingerprint(manifest),
        process_id=123, source_fingerprint=manifest.source_fingerprint, interpreter_fingerprint=manifest.interpreter_fingerprint)
    assert not receipt_matches(manifest.model_copy(update={"instance_id": "rti_" + "0" * 32}), receipt, owned_process_id=123)
    assert not receipt_matches(manifest.model_copy(update={"interpreter_fingerprint": "0" * 64}), receipt, owned_process_id=123)


def test_copy_rejects_changed_source_and_does_not_publish_manifest(tmp_path: Path):
    source, _, manifest, _ = _fixture(tmp_path)
    (source / "server.py").write_text("changed", encoding="utf-8")
    store = tmp_path / "other-artifacts"
    with pytest.raises(ValueError):
        create_runtime_artifact(source, store, files=manifest.files, entry_module="server",
            interpreter_fingerprint=manifest.interpreter_fingerprint)
    assert not list(store.glob("*/launch.json"))
