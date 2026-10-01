# 控制者和独立 Runner 共用的只读运行对应核验；未知所有权、漂移和错实例一律不确认。
from pathlib import Path

from product.backend.infra.runtime.process.artifact import read_runtime_manifest, verify_runtime_artifact
from product.backend.infra.runtime.process.tree import kernel_process_created_at
from product.protocols.runtime_identity import ControlledRuntimeReference, RuntimeLaunchReceipt, receipt_matches, runtime_manifest_fingerprint


def runtime_artifact_store(var_dir: Path) -> Path:
    return var_dir.resolve() / "runtime" / "target-artifacts"


def runtime_corresponds(var_dir: Path, reference: ControlledRuntimeReference) -> bool:
    """核对固定运行副本、控制者回执以及 OS 进程创建身份，不请求目标应用。"""
    try:
        store = runtime_artifact_store(var_dir)
        root = store / reference.instance_id
        if root.resolve() != root or not root.is_dir():
            return False
        identity = {"kind": "windows-job", "name": "jiejian-sample-" + reference.owner_id}
        if kernel_process_created_at(identity, reference.process_id) != reference.process_created_at:
            return False
        manifest = read_runtime_manifest(root / "launch.json")
        if manifest.instance_id != reference.instance_id or manifest.source_fingerprint != reference.source_fingerprint:
            return False
        if runtime_manifest_fingerprint(manifest) != reference.manifest_fingerprint:
            return False
        path = root / "started.json"
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 4096:
            return False
        with path.open("rb") as stream:
            raw = stream.read(4097)
        if len(raw) > 4096:
            return False
        receipt = RuntimeLaunchReceipt.model_validate_json(raw)
        if not receipt_matches(manifest, receipt, owned_process_id=reference.process_id):
            return False
        verify_runtime_artifact(root / "source", manifest)
        return kernel_process_created_at(identity, reference.process_id) == reference.process_created_at
    except (OSError, ValueError):
        return False
