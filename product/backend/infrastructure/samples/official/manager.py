# 管理单个官方示例进程的启动、恢复和关闭。
from __future__ import annotations

import json
import ast
import re
import shutil
import subprocess
import time
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from threading import RLock
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import uuid4
import httpx
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.infrastructure.runtime.paths import RuntimePaths
from product.backend.infrastructure.runtime.process.environment import ProcessEnvironmentRole, process_environment_failure_summary, spawn_python_module
from product.backend.infrastructure.runtime.process.tree import controller_for, kernel_process_created_at, process_tree_has_exited, release_process_tree, terminate_process_tree
from product.backend.infrastructure.runtime.process.controlled.artifact import create_runtime_artifact, python_runtime_files
from product.backend.infrastructure.runtime.process.controlled.correspondence import runtime_artifact_store, runtime_corresponds
from product.protocols.runtime.runtime_identity import ControlledRuntimeReference, RuntimeLaunchReceipt, receipt_matches, runtime_manifest_fingerprint, runtime_source_fingerprint
from .artifacts import _AUTHORIZATION_POLICY_FILE, _SECRET_NAMES, _append_event, _descriptor_origin, _new_secret_values, _process_state, _validate_behavior, _write_authorization_policy, _write_check_descriptor, _write_control, _write_text_atomic
from .installation import _copy_source, _load_installation
from .models import AuthorizationOrder, BlobObservation, OfficialSampleRuntime, OwnerObservation, ProcessLauncher


_EXPERIENCE_ID = re.compile(r"exp_[0-9a-f]{32}\Z")


class OfficialSampleManager:
    """管理当前 ApplicationCore 中至多一个官方 Sample 进程。"""

    def __init__(
        self,
        var_dir: Path,
        official_sample_root: Path | None,
        environment: Mapping[str, str],
        *,
        process_launcher: ProcessLauncher = spawn_python_module,
        health_timeout_seconds: float = 10.0,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._paths = RuntimePaths(var_dir).ensure_layout()
        self._environment = dict(environment)
        self._process_launcher = process_launcher
        self._health_timeout_seconds = health_timeout_seconds
        self._monotonic = monotonic
        self._sleeper = sleeper
        self._lock = RLock()
        self._active: OfficialSampleRuntime | None = None
        self.installation = _load_installation(official_sample_root)

    @property
    def active(self) -> OfficialSampleRuntime | None:
        with self._lock:
            runtime = self._active
            if runtime is not None and process_tree_has_exited(runtime.process):
                release_process_tree(runtime.process)
                self._active = None
                runtime = None
            return runtime

    def start(
        self,
        *,
        experience_id: str | None = None,
        authorization_order: AuthorizationOrder = "ENQUEUE_BEFORE_AUTHORIZE",
        owner_observation: OwnerObservation = "AVAILABLE",
        blob_observation: BlobObservation = "AVAILABLE",
        execution_mode: Literal["SYNCHRONOUS", "QUEUED"] = "QUEUED",
        workspace_id: str | None = None,
    ) -> OfficialSampleRuntime:
        """复制官方源码并以动态端口启动；任一步失败都回收已创建进程。"""

        _validate_behavior(
            authorization_order,
            owner_observation,
            blob_observation,
        )
        with self._lock:
            if self.active is not None:
                raise JiejianError(
                    ErrorCode.OFFICIAL_SAMPLE_CONFLICT,
                    "已有官方示例正在运行",
                )
            installation = self.installation
            if not installation.available or installation.source is None:
                raise JiejianError(
                    ErrorCode.OFFICIAL_SAMPLE_UNAVAILABLE,
                    "官方示例当前不可用",
                )
            clean_id = experience_id or f"exp_{uuid4().hex}"
            if _EXPERIENCE_ID.fullmatch(clean_id) is None:
                raise JiejianError(
                    ErrorCode.STATE_PRECONDITION,
                    "官方示例体验标识无效",
                )
            experience_root = self._paths.official_sample_runtime / clean_id
            source_root = experience_root / "source" if workspace_id is None else self.workspace_source(workspace_id)
            runtime_root = experience_root / "state"
            log_path = self._paths.logs / "official-samples" / f"{clean_id}.log"
            if experience_root.exists() or log_path.exists():
                raise JiejianError(
                    ErrorCode.OFFICIAL_SAMPLE_CONFLICT,
                    "官方示例体验目录已经存在",
                )
            if not source_root.exists():
                _copy_source(installation.source, source_root)
                _write_authorization_policy(source_root / _AUTHORIZATION_POLICY_FILE, authorization_order, execution_mode)
            elif workspace_id is None or not source_root.is_dir():
                raise JiejianError(ErrorCode.OFFICIAL_SAMPLE_CONFLICT, "示例源码目录不可用")
            runtime_root.mkdir(parents=True, exist_ok=False)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            control_path = runtime_root / "control.json"
            _write_control(
                control_path,
                authorization_order,
                owner_observation,
                blob_observation,
            )
            secret_values = _new_secret_values(runtime_root)
            child_environment = dict(self._environment)
            child_environment.update(
                {name: secret_values[name] for name in _SECRET_NAMES}
            )
            process: subprocess.Popen[Any] | None = None
            try:
                launch_root, launch_manifest = create_runtime_artifact(source_root, runtime_artifact_store(self._paths.root),
                    files=python_runtime_files(source_root), entry_module=installation.entry_module or "server",
                    interpreter_fingerprint=self._environment.get("JIEJIAN_RUNTIME_FINGERPRINT", "0" * 64))
                with log_path.open("ab", buffering=0) as log_stream:
                    from product.backend.infrastructure.runtime.generated_files import register_generated_file
                    register_generated_file(self._paths.root, log_path, 'sample-log')
                    process = self._process_launcher(
                        child_environment,
                        "product.backend.infrastructure.runtime.process.controlled.target",
                        "--manifest", str(launch_root / "launch.json"), "--",
                        "--runtime-root",
                        str(runtime_root),
                        "--port",
                        "0",
                        role=ProcessEnvironmentRole.SAMPLE,
                        secret_names=_SECRET_NAMES,
                        cwd=launch_root / "source",
                        stdout=log_stream,
                        stderr=subprocess.STDOUT,
                        stdin=subprocess.DEVNULL,
                        tree_name=f"jiejian-sample-{clean_id}",
                    )
                descriptor_path, origin = self._wait_until_healthy(
                    process,
                    runtime_root,
                    installation.health_path or "/health",
                )
                receipt = RuntimeLaunchReceipt.model_validate_json((launch_root / "started.json").read_bytes())
                if not receipt_matches(launch_manifest, receipt, owned_process_id=process.pid):
                    raise JiejianError(ErrorCode.OFFICIAL_SAMPLE_START_FAILED, "受控启动回执不匹配")
                _write_check_descriptor(descriptor_path, runtime_root, origin)
                active = OfficialSampleRuntime(
                    experience_id=clean_id,
                    sample_id=installation.sample_id,
                    display_name=installation.display_name,
                    origin=origin,
                    experience_root=experience_root,
                    source_root=source_root,
                    runtime_root=runtime_root,
                    descriptor_path=descriptor_path,
                    control_path=control_path,
                    log_path=log_path,
                    process=process,
                    secrets=secret_values,
                    launch_manifest=launch_manifest,
                )
                self._active = active
                _append_event(log_path, "OFFICIAL_SAMPLE_STARTED", origin=origin)
                return active
            except Exception as exc:
                process_state = _process_state(process)
                diagnostic = (
                    process_environment_failure_summary(exc)
                    if isinstance(exc, JiejianError)
                    else {}
                )
                if process is not None:
                    try:
                        terminate_process_tree(process, 3.0)
                    except Exception:
                        pass
                secret_values.clear()
                shutil.rmtree(experience_root, ignore_errors=True)
                try:
                    _append_event(
                        log_path,
                        "OFFICIAL_SAMPLE_START_FAILED",
                        error_code=(
                            exc.code
                            if isinstance(exc, JiejianError)
                            else ErrorCode.OFFICIAL_SAMPLE_START_FAILED.value
                        ),
                        failure_type=type(exc).__name__,
                        process_state=process_state,
                        reason=(
                            str(diagnostic["reason"])
                            if diagnostic.get("reason") is not None
                            else None
                        ),
                        missing_names=(
                            tuple(str(name) for name in diagnostic["missing_names"])
                            if isinstance(diagnostic.get("missing_names"), list)
                            else None
                        ),
                    )
                except Exception:
                    # 日志写入失败不能覆盖启动首错。
                    pass
                if isinstance(exc, JiejianError):
                    raise
                raise JiejianError(
                    ErrorCode.OFFICIAL_SAMPLE_START_FAILED,
                    "官方示例未能在有界时间内启动",
                ) from exc

    def switch_behavior(
        self,
        experience_id: str,
        *,
        authorization_order: AuthorizationOrder,
        owner_observation: OwnerObservation,
        blob_observation: BlobObservation,
        execution_mode: Literal["SYNCHRONOUS", "QUEUED"] = "QUEUED",
    ) -> OfficialSampleRuntime:
        """只切换真实代码和观察开关；业务恢复由原资源撤销完成，不清除历史。"""

        _validate_behavior(
            authorization_order,
            owner_observation,
            blob_observation,
        )
        with self._lock:
            runtime = self._require_active(experience_id)
            policy_path = runtime.source_root / _AUTHORIZATION_POLICY_FILE
            previous_policy = policy_path.read_text(encoding="utf-8")
            try:
                _write_authorization_policy(policy_path, authorization_order, execution_mode)
                _write_control(
                    runtime.control_path,
                    authorization_order,
                    owner_observation,
                    blob_observation,
                )
            except (httpx.HTTPError, OSError) as exc:
                try:
                    _write_text_atomic(policy_path, previous_policy)
                except OSError:
                    pass
                raise JiejianError(
                    ErrorCode.OFFICIAL_SAMPLE_START_FAILED,
                    "官方示例行为切换失败",
                ) from exc
            _append_event(runtime.log_path, "OFFICIAL_SAMPLE_BEHAVIOR_CHANGED")
            return self.reload_source(experience_id)

    def runtime_reference(self, experience_id: str) -> ControlledRuntimeReference | None:
        """只在本控制者拥有当前进程、且回执和副本匹配时返回可冻结身份。"""
        runtime = self._require_active(experience_id)
        manifest = runtime.launch_manifest
        controller = controller_for(runtime.process)
        if manifest is None or controller is None or controller.has_exited():
            return None
        created = kernel_process_created_at(controller.kernel_identity, runtime.process.pid)
        if created is None:
            return None
        reference = ControlledRuntimeReference(instance_id=manifest.instance_id,
            manifest_fingerprint=runtime_manifest_fingerprint(manifest), source_fingerprint=manifest.source_fingerprint,
            process_id=runtime.process.pid, process_created_at=created, owner_id=runtime.experience_id)
        return reference if runtime_corresponds(self._paths.root, reference) else None

    def reload_source(self, experience_id: str, *, expected_source_fingerprint: str | None = None) -> OfficialSampleRuntime:
        """显式加载独立代码副本，确认原进程退出后沿用当前本机端口与业务运行数据。"""
        with self._lock:
            runtime = self._require_active(experience_id)
            controller = controller_for(runtime.process)
            if controller is None or controller.has_exited():
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "不能确认当前示例进程的控制权")
            files = python_runtime_files(runtime.source_root)
            if expected_source_fingerprint is not None and runtime_source_fingerprint(files) != expected_source_fingerprint:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "当前源码与本批交付不一致，不能加载")
            if runtime.launch_manifest is not None and runtime.launch_manifest.files == files and self.runtime_reference(experience_id) is not None:
                return runtime
            launch_root, manifest = create_runtime_artifact(runtime.source_root, runtime_artifact_store(self._paths.root),
                files=files, entry_module=self.installation.entry_module or "server",
                interpreter_fingerprint=self._environment.get("JIEJIAN_RUNTIME_FINGERPRINT", "0" * 64))
            environment = dict(self._environment)
            environment.update(runtime.secrets)
            terminate_process_tree(runtime.process, 3.0)
            self._active = None
            process = None
            try:
                with runtime.log_path.open("ab", buffering=0) as stream:
                    from product.backend.infrastructure.runtime.generated_files import register_generated_file
                    register_generated_file(self._paths.root, runtime.log_path, 'sample-log')
                    process = self._process_launcher(environment, "product.backend.infrastructure.runtime.process.controlled.target",
                        "--manifest", str(launch_root / "launch.json"), "--", "--runtime-root", str(runtime.runtime_root),
                        "--port", str(urlsplit(runtime.origin).port), role=ProcessEnvironmentRole.SAMPLE,
                        secret_names=_SECRET_NAMES, cwd=launch_root / "source", stdout=stream,
                        stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, tree_name=f"jiejian-sample-{experience_id}")
                descriptor, origin = self._wait_until_healthy(process, runtime.runtime_root, self.installation.health_path or "/health")
                receipt = RuntimeLaunchReceipt.model_validate_json((launch_root / "started.json").read_bytes())
                if origin != runtime.origin or not receipt_matches(manifest, receipt, owned_process_id=process.pid):
                    raise JiejianError(ErrorCode.OFFICIAL_SAMPLE_START_FAILED, "新运行实例的地址或回执不一致")
                _write_check_descriptor(descriptor, runtime.runtime_root, origin)
                updated = replace(runtime, process=process, launch_manifest=manifest)
                self._active = updated
                return updated
            except Exception:
                if process is not None:
                    terminate_process_tree(process, 3.0)
                raise

    def resolve_secret_names(self, names: tuple[str, ...] | list[str]) -> dict[str, str]:
        """只返回当前活跃体验明确请求的观察秘密。"""

        runtime = self.active
        if runtime is None:
            return {}
        requested = set(names)
        return {
            name: value
            for name, value in runtime.secrets.items()
            if name in requested
        }

    def set_observation(self, experience_id: str, *, available: bool) -> None:
        """观察支线只替换非秘密控制字段，不重写 Agent 正在维护的源码。"""
        with self._lock:
            runtime = self._require_active(experience_id)
            payload = json.loads(runtime.control_path.read_text(encoding="utf-8"))
            payload.update(owner_observation="AVAILABLE" if available else "UNAVAILABLE",
                           blob_observation="AVAILABLE" if available else "UNAVAILABLE")
            _write_text_atomic(runtime.control_path, json.dumps(payload, ensure_ascii=False, sort_keys=True))

    def export_execution_mode(self, experience_id: str) -> str:
        """只解析预设声明，不在 API 进程执行应用源码；复杂改写要求用户自行录制。"""
        with self._lock:
            runtime = self._require_active(experience_id)
            path = runtime.source_root / _AUTHORIZATION_POLICY_FILE
            try:
                if path.stat().st_size > 16384:
                    raise ValueError("policy too large")
                tree = ast.parse(path.read_text(encoding="utf-8-sig"))
                functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "export_execution_mode"]
                if len(functions) != 1:
                    raise ValueError("mode unavailable")
                body = functions[0].body
                executable = [node for node in body if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str))]
                if len(executable) != 1 or not isinstance(executable[0], ast.Return):
                    raise ValueError("mode is not a literal")
                mode = ast.literal_eval(executable[0].value)
                if mode not in {"SYNCHRONOUS", "QUEUED"}:
                    raise ValueError("mode invalid")
                return mode
            except (OSError, ValueError, SyntaxError, TypeError):
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "当前源码已超出预设材料范围，请自行录制当前导出动作") from None

    def bind_effects(self, experience_id: str, *, export_effect_id: str, view_effect_id: str) -> None:
        """仅活动体验在正式批准后写入公开效果映射，不更改源码或观察标准。"""
        with self._lock:
            runtime=self._require_active(experience_id)
            if any(re.fullmatch(r"bef_[0-9a-f]{32}",value) is None for value in (export_effect_id,view_effect_id)):
                raise JiejianError(ErrorCode.STATE_PRECONDITION,"官方示例效果映射无效")
            payload=json.loads(runtime.control_path.read_text(encoding="utf-8"))
            payload.update(export_effect_id=export_effect_id,view_effect_id=view_effect_id)
            _write_text_atomic(runtime.control_path,json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")))

    def copy_node_source(self, workspace_id: str) -> Path:
        """只复制已校验的Node源码；运行仍由通用Runtime Worker拥有。"""
        installation = self.installation
        if not installation.available or installation.runtime_kind != 'NODE_ESM':
            raise JiejianError(ErrorCode.OFFICIAL_SAMPLE_START_FAILED,'Node示例安装不可用')
        target=self.workspace_source(workspace_id)
        if target.exists():
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'工作空间已存在，不能覆盖已有代码')
        _copy_source(installation.source,target)
        return target

    def workspace_source(self, workspace_id: str) -> Path:
        """只解析受控工作空间；持久源码与包含临时秘密的实例目录隔离。"""
        if re.fullmatch(r"wsp_[0-9a-f]{32}", workspace_id) is None:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "示例工作空间标识无效")
        root = self._paths.official_sample_runtime.parent / "workspaces"
        path = root / workspace_id / "source"
        if path.resolve() != path.absolute() or not path.resolve().is_relative_to(root.absolute()):
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "示例工作空间目录越界")
        return path

    def cleanup_exited_instance(self, instance_id: str, identity: dict) -> None:
        """明确确认旧受控树已退出后清理实例目录；持久源码目录不在此范围。"""
        from product.backend.infrastructure.runtime.process.tree import kernel_tree_has_exited
        if _EXPERIENCE_ID.fullmatch(instance_id) is None or identity != {"kind": "windows-job", "name": f"jiejian-sample-{instance_id}"} or not kernel_tree_has_exited(identity):
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "旧实例退出尚未确认，不能清理运行数据")
        root = self._paths.official_sample_runtime.absolute()
        path = root / instance_id
        if path.resolve() != path.absolute() or not path.resolve().is_relative_to(root):
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "示例实例目录越界")
        if path.exists():
            shutil.rmtree(path)

    def stop(self, experience_id: str | None = None) -> None:
        """回收当前 Sample 进程树和会话目录；只保留独立历史日志。"""

        with self._lock:
            runtime = self._active
            if runtime is None:
                return
            if experience_id is not None and runtime.experience_id != experience_id:
                raise JiejianError(
                    ErrorCode.OFFICIAL_SAMPLE_CONFLICT,
                    "指定的官方示例体验不是当前活跃体验",
                )
            self._active = None
            termination_error: Exception | None = None
            try:
                terminate_process_tree(runtime.process, 3.0)
            except Exception as exc:  # pragma: no cover - 由平台进程树测试覆盖
                termination_error = exc
            runtime.secrets.clear()
            try:
                _append_event(runtime.log_path, "OFFICIAL_SAMPLE_STOPPED")
            except Exception as exc:
                if termination_error is None:
                    termination_error = exc
            try:
                shutil.rmtree(runtime.experience_root)
            except OSError:
                if termination_error is None:
                    termination_error = JiejianError(
                        ErrorCode.OFFICIAL_SAMPLE_START_FAILED, "官方示例运行目录清理失败")
            if termination_error is not None:
                # 尝试既有清理步骤后仍抛第一主错，不用后续日志或目录错误覆盖它。
                raise termination_error

    def _require_active(self, experience_id: str) -> OfficialSampleRuntime:
        runtime = self.active
        if runtime is None or runtime.experience_id != experience_id:
            raise JiejianError(
                ErrorCode.OFFICIAL_SAMPLE_CONFLICT,
                "官方示例体验当前未运行",
            )
        return runtime

    def _wait_until_healthy(
        self,
        process: subprocess.Popen[Any],
        runtime_root: Path,
        health_path: str,
    ) -> tuple[Path, str]:
        descriptor_path = runtime_root / "environment.json"
        deadline = self._monotonic() + self._health_timeout_seconds
        while self._monotonic() < deadline:
            if process_tree_has_exited(process):
                break
            try:
                descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
                origin = _descriptor_origin(descriptor)
                with httpx.Client(trust_env=False, follow_redirects=False) as client:
                    response = client.get(
                        f"{origin}{health_path}",
                        timeout=0.75,
                    )
                    if response.status_code == 200:
                        return descriptor_path, origin
            except (OSError, UnicodeError, json.JSONDecodeError, httpx.HTTPError, JiejianError):
                pass
            self._sleeper(0.05)
        raise JiejianError(
            ErrorCode.OFFICIAL_SAMPLE_START_FAILED,
            "官方示例未能在有界时间内启动",
        )
