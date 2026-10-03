# Runtime Worker持有的Node进程：先核对冻结输入和内核归属，再放行目标并核对监听者。
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import subprocess
import time

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.runtime.process.controlled.artifact import _read_bounded, _regular_file, verify_runtime_artifact
from product.backend.infra.runtime.process.listeners import ipv4_listeners
from product.backend.infra.runtime.process.tree import (
    controller_for, kernel_process_created_at, spawn_managed_process, terminate_process_tree,
)
from product.protocols.runtime.node_runtime import NodeRuntimeManifest, NodeRuntimeLoadRequest, NodeRuntimeReference, node_document_fingerprint
from product.protocols.runtime.runtime_identity import MAX_MANIFEST_BYTES

EXECUTOR = Path(__file__).with_name("node_target.mjs")


def node_artifact_store(var_dir: Path) -> Path:
    return var_dir.resolve() / "runtime" / "node-artifacts"


def read_node_manifest(var_dir: Path, request: NodeRuntimeLoadRequest) -> tuple[Path, NodeRuntimeManifest]:
    root = node_artifact_store(var_dir) / request.instance_id
    if root.resolve() != root or not root.is_dir():
        raise JiejianError(ErrorCode.STATE_PRECONDITION, "冻结的运行副本不可用")
    manifest = NodeRuntimeManifest.model_validate_json(_read_bounded(_regular_file(root, "launch.json"), MAX_MANIFEST_BYTES))
    if (manifest.project_id != request.project_id or manifest.instance_id != request.instance_id
            or node_document_fingerprint(manifest) != request.manifest_fingerprint
            or manifest.source_fingerprint != request.source_fingerprint):
        raise JiejianError(ErrorCode.STATE_PRECONDITION, "运行副本与本次加载输入不一致")
    verify_runtime_artifact(root / "source", manifest)
    return root, manifest


def _digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 512 * 1024 * 1024:
        raise JiejianError(ErrorCode.STATE_PRECONDITION, "运行程序身份不可核对")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def node_execution_identity(node_executable: Path) -> dict[str, str]:
    """按解释器、固定执行器顺序核验身份；路径与摘要算法由运行基础设施拥有。"""
    return {"interpreter_fingerprint": _digest(node_executable), "executor_fingerprint": _digest(EXECUTOR)}


def node_reference_matches(var_dir: Path, request: NodeRuntimeLoadRequest, reference: NodeRuntimeReference,
        node_executable: Path) -> bool:
    """只核对本次输入、冻结副本、内核创建身份及精确loopback监听者；不发送目标请求。"""
    if (reference.project_id!=request.project_id or reference.instance_id!=request.instance_id
            or reference.manifest_fingerprint!=request.manifest_fingerprint or reference.source_fingerprint!=request.source_fingerprint):
        return False
    return node_corresponds(var_dir,reference,node_executable)


def node_corresponds(var_dir: Path, reference: NodeRuntimeReference, node_executable: Path) -> bool:
    """独立Runner只消费冻结实例引用，不从PID、端口或目标自报内容推断归属。"""
    try:
        identity = {"kind": "windows-job", "name": "jiejian-node-" + reference.instance_id}
        before = kernel_process_created_at(identity, reference.process_id)
        if (before != reference.process_created_at
                or ipv4_listeners(reference.port) != (("127.0.0.1", reference.process_id),)):
            return False
        root=node_artifact_store(var_dir)/reference.instance_id
        if root.resolve()!=root or not root.is_dir():
            return False
        manifest=NodeRuntimeManifest.model_validate_json(_read_bounded(_regular_file(root,'launch.json'),MAX_MANIFEST_BYTES))
        verify_runtime_artifact(root/'source',manifest)
        if (reference.project_id != manifest.project_id or reference.instance_id != manifest.instance_id
                or reference.manifest_fingerprint != node_document_fingerprint(manifest)
                or reference.source_fingerprint != manifest.source_fingerprint or reference.port != manifest.port
                or _digest(node_executable) != manifest.interpreter_fingerprint
                or _digest(EXECUTOR) != manifest.executor_fingerprint):
            return False
        return kernel_process_created_at(identity, reference.process_id) == before
    except (OSError, ValueError, JiejianError):
        return False


@dataclass
class OwnedNodeProcess:
    process: subprocess.Popen
    reference: NodeRuntimeReference
    record_server: object | None = None

    def stop(self):
        # 只有目标树已确认退出才释放独占记录句柄；退出失败时继续保留来源保护。
        terminate_process_tree(self.process, timeout=5)
        if self.record_server is not None:
            self.record_server.stop()
            self.record_server = None


def start_owned_node(var_dir: Path, request: NodeRuntimeLoadRequest, node_executable: Path,
        *, environ: dict[str, str], timeout: float = 15, cancelled=lambda: False, record_owner_identity=None) -> OwnedNodeProcess:
    """仅供Runtime Worker执行；失败回收本次拥有的树，不停止外部占用端口的进程。"""
    if os.name != "nt" or not 0 < timeout <= 30 or not node_executable.is_absolute():
        raise JiejianError(ErrorCode.STATE_PRECONDITION, "当前系统不支持这种受控运行方式")
    root, manifest = read_node_manifest(var_dir, request)
    if (_digest(node_executable) != manifest.interpreter_fingerprint
            or _digest(EXECUTOR) != manifest.executor_fingerprint):
        raise JiejianError(ErrorCode.STATE_PRECONDITION, "解释器或受控加载器发生变化")
    gate = root / "start.gate"
    if gate.exists():
        raise JiejianError(ErrorCode.STATE_PRECONDITION, "该实例已有启动痕迹，请查询原操作")
    if cancelled() or ipv4_listeners(manifest.port):
        raise JiejianError(ErrorCode.STATE_PRECONDITION, "加载已取消或目标端口被其他进程占用")
    data = var_dir.resolve() / "data" / "controlled-applications" / request.project_id
    if data.resolve() != data:
        raise JiejianError(ErrorCode.STATE_PRECONDITION, "运行数据目录含有链接")
    data.mkdir(parents=True, exist_ok=True)
    environment = {key.upper(): value for key, value in environ.items() if key.upper() in {"SYSTEMROOT", "WINDIR"}}
    raw_hash = hashlib.sha256(_read_bounded(root / "launch.json", MAX_MANIFEST_BYTES)).hexdigest()
    argv = [str(node_executable), "--experimental-vm-modules", "--permission",
        f"--allow-fs-read={root}", f"--allow-fs-read={EXECUTOR}", f"--allow-fs-read={data}",
        f"--allow-fs-write={data}", str(EXECUTOR), str(root / "launch.json"), raw_hash, str(data)]
    from product.backend.infra.runtime.process.records.record_server import OwnedRecordServer
    records = OwnedRecordServer(var_dir, request.project_id, request.instance_id)
    # 记录库位于目标 fs 权限之外；只给受控宿主业务端口能力，令牌不进入清单、回执或应用 env。
    environment.update(JIEJIAN_RECORD_ORIGIN=records.origin, JIEJIAN_RECORD_CAPABILITY=records.token,
        JIEJIAN_RECORD_CONTROL=records.control_token)
    try:
        if record_owner_identity is not None:
            provider = records.reference(request.project_id, record_owner_identity)
            with (root / 'record-provider.json').open('x', encoding='utf-8') as stream:
                stream.write(provider.model_dump_json())
        process = spawn_managed_process(argv, tree_name="jiejian-node-" + request.instance_id,
            cwd=data, env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW)
    except BaseException:
        records.stop()
        raise
    try:
        controller = controller_for(process)
        created = None if controller is None else kernel_process_created_at(controller.kernel_identity, process.pid)
        if created is None or cancelled():
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "运行进程归属尚未确认或加载已取消")
        # 确认进入拥有的进程树之后才允许应用模块执行；门闸只写一次。
        with gate.open("x", encoding="ascii") as stream:
            stream.write(raw_hash)
        reference = NodeRuntimeReference(project_id=request.project_id, instance_id=request.instance_id,
            manifest_fingerprint=request.manifest_fingerprint, source_fingerprint=request.source_fingerprint,
            process_id=process.pid, process_created_at=created, port=manifest.port)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if process.poll() is not None or cancelled():
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "目标入口未能保持运行或加载已取消")
            if node_reference_matches(var_dir, request, reference, node_executable):
                return OwnedNodeProcess(process, reference, records)
            time.sleep(.05)
        raise JiejianError(ErrorCode.STATE_PRECONDITION, "未确认本次进程拥有指定监听端口")
    except BaseException as primary:
        try:
            terminate_process_tree(process, timeout=5)
            records.stop()
        except JiejianError:
            code = primary.code if isinstance(primary, JiejianError) else ErrorCode.TARGET_EXECUTION_FAILED
            raise JiejianError(code, "运行加载失败，且本次进程树退出尚未确认",
                details={"cleanup_issue": "PROCESS_TREE_FAILED"}) from None
        raise
