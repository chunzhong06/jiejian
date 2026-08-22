# =============================================================================
# Execution 最小子进程环境
#
# 定位
#   所有产品 Python 子进程的解释器、环境、cwd 与启动闸门边界
#
# 职责
#   确认绝对解释器｜筛选最小环境｜按需注入授权 secret｜绑定进程树后放行模块
#
# 边界
#   只传播 allowlist 与显式授权名称；调用方不得以完整 os.environ 绕过筛选。
#
# 调用链
#   Worker / Runner / Recording / Observer / Demo → spawn_python_module → process tree
# =============================================================================

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.infra.runtime.process_tree import ProcessTreeController, controller_for, release_process_tree, spawn_managed_process, terminate_process_tree

_BASE_KEYS = (
    "COMSPEC",
    "PATHEXT",
    "PLAYWRIGHT_BROWSERS_PATH",
    "JIEJIAN_PYTHON_EXECUTABLE",
    "JIEJIAN_PYTHON_ENVIRONMENT_PATH",
    "JIEJIAN_PYTHON_ENVIRONMENT_TYPE",
    "JIEJIAN_PROJECT_ROOT",
    "JIEJIAN_RUNTIME_FINGERPRINT",
    "JIEJIAN_RUNTIME_MODE",
    "JIEJIAN_TOOLCHAIN_MANIFEST",
    "JIEJIAN_VAR_DIR",
    "JIEJIAN_UV_EXECUTABLE",
    "JIEJIAN_UV_VERSION",
    "JIEJIAN_NODE_EXECUTABLE",
    "JIEJIAN_NODE_VERSION",
    "JIEJIAN_PNPM_EXECUTABLE",
    "JIEJIAN_PNPM_VERSION",
    "JIEJIAN_PLAYWRIGHT_EXECUTABLE",
    "JIEJIAN_FRONTEND_DEPENDENCIES",
    "JIEJIAN_FRONTEND_DIST",
    "JIEJIAN_SERVE_LOCK_PATH",
    "JIEJIAN_SERVE_OWNER_TOKEN",
    "SYSTEMROOT",
    "WINDIR",
)


def minimal_process_environment(
    source: Mapping[str, str],
    *,
    secret_names: Sequence[str] = (),
) -> dict[str, str]:
    """只传递 Python 运行所需键和本次快照引用的秘密。"""

    selected_names = tuple(dict.fromkeys((*_BASE_KEYS, *secret_names)))
    by_casefold = {key.casefold(): (key, value) for key, value in source.items()}
    result: dict[str, str] = {}
    for name in selected_names:
        selected = by_casefold.get(name.casefold())
        if selected is not None and selected[1]:
            result[name] = selected[1]
    executable = confirmed_python_executable(source)
    result["JIEJIAN_PYTHON_EXECUTABLE"] = executable
    system_root = result.get("SYSTEMROOT") or result.get("WINDIR")
    path_entries = [str(Path(executable).parent)]
    if system_root:
        path_entries.append(str(Path(system_root) / "System32"))
    result["PATH"] = os.pathsep.join(dict.fromkeys(path_entries))
    var_dir = result.get("JIEJIAN_VAR_DIR")
    if var_dir:
        temporary = RuntimePaths(Path(var_dir)).temp
        temporary.mkdir(parents=True, exist_ok=True)
        result["TEMP"] = str(temporary)
        result["TMP"] = str(temporary)
    result["PYTHONDONTWRITEBYTECODE"] = "1"
    result["PYTHONNOUSERSITE"] = "1"
    result["PYTHONUTF8"] = "1"
    result.pop("PYTHONPATH", None)
    result.pop("PYTHONHOME", None)
    return result


def confirmed_python_executable(source: Mapping[str, str]) -> str:
    """返回与当前进程完全一致的绝对解释器；配置漂移立即失败。"""

    current = Path(sys.executable).resolve()
    configured = source.get("JIEJIAN_PYTHON_EXECUTABLE")
    expected = Path(configured).resolve() if configured else current
    if expected != current or not expected.is_file():
        raise JiejianError(
            ErrorCode.RUNTIME_ENVIRONMENT_INVALID,
            "当前 Python 与界鉴启动阶段确认的解释器不一致",
            details={"expected": str(expected), "actual": str(current)},
        )
    return str(expected)


def python_module_command(
    source: Mapping[str, str],
    module: str,
    *arguments: str,
) -> list[str]:
    """构造所有产品 Python 子进程共用的绝对解释器模块命令。"""

    return [confirmed_python_executable(source), "-B", "-m", module, *arguments]


def spawn_python_module(
    source: Mapping[str, str],
    module: str,
    *arguments: str,
    secret_names: Sequence[str] = (),
    extra_environment: Mapping[str, str] | None = None,
    allowed_extra_names: Sequence[str] = (),
    cwd: Path,
    popen: Callable[..., subprocess.Popen[Any]] | None = None,
    python_executable: str | None = None,
    tree_name: str | None = None,
    before_release: Callable[[subprocess.Popen[Any], ProcessTreeController], None]
    | None = None,
    **kwargs: Any,
) -> subprocess.Popen[Any]:
    """以受控解释器启动模块，并在内核进程树绑定完成后才放行模块代码。"""

    working_directory = cwd.resolve()
    if not working_directory.is_dir():
        raise JiejianError(
            ErrorCode.RUNTIME_ENVIRONMENT_INVALID,
            "Python 子进程工作目录不存在",
            details={"cwd": str(working_directory)},
        )
    environment = minimal_process_environment(source, secret_names=secret_names)
    for name, value in (extra_environment or {}).items():
        if (not name.startswith("JIEJIAN_") and name not in allowed_extra_names) or name in {
            "JIEJIAN_PYTHON_EXECUTABLE",
            "JIEJIAN_PYTHON_ENVIRONMENT_PATH",
            "JIEJIAN_RUNTIME_FINGERPRINT",
            "JIEJIAN_RUNTIME_MODE",
            "JIEJIAN_VAR_DIR",
        }:
            raise JiejianError(
                ErrorCode.RUNTIME_ENVIRONMENT_INVALID,
                "Python 子进程附加环境变量越界",
                details={"name": name},
            )
        if value:
            environment[name] = value

    executable = confirmed_python_executable(environment)
    if python_executable is not None:
        # 仅保留给直接进程边界测试注入失败解释器；生产调用方不传此参数。
        executable = str(Path(python_executable).resolve())
    gate_root = _process_gate_root(environment, working_directory)
    gate_root.mkdir(parents=True, exist_ok=True)
    gate_path = gate_root / f"gate-{uuid4().hex}.ready"
    command = [
        executable,
        "-B",
        "-m",
        "product.backend.infra.runtime.process_bootstrap",
        "--gate",
        str(gate_path),
        "--module",
        module,
        "--",
        *arguments,
    ]
    process: subprocess.Popen[Any] | None = None
    try:
        # 运行时解析默认 Popen，使模块级测试替身可见；真实入口仍由进程树模块识别原生句柄。
        launcher = subprocess.Popen if popen is None else popen
        process = spawn_managed_process(
            command,
            popen=launcher,
            tree_name=tree_name,
            cwd=str(working_directory),
            env=environment,
            **kwargs,
        )
        controller = controller_for(process)
        if before_release is not None:
            if controller is None:
                raise JiejianError(
                    ErrorCode.PROCESS_TREE_FAILED,
                    "Python 子进程缺少进程树控制器",
                )
            before_release(process, controller)
        # 原子创建是子进程开始执行目标模块的唯一信号；此时 Job/session 已完成绑定。
        temporary = gate_path.with_suffix(".tmp")
        temporary.write_text("ready\n", encoding="ascii")
        os.replace(temporary, gate_path)
        return process
    except Exception as exc:
        cleanup_failed = False
        if process is not None:
            try:
                terminate_process_tree(process, 2.0)
            except Exception:
                cleanup_failed = True
        gate_path.unlink(missing_ok=True)
        gate_path.with_suffix(".tmp").unlink(missing_ok=True)
        if cleanup_failed:
            raise JiejianError(
                ErrorCode.PROCESS_TREE_FAILED,
                "Python 子进程启动失败且进程树未能回收",
            ) from exc
        raise


def _process_gate_root(environment: Mapping[str, str], cwd: Path) -> Path:
    var_dir = environment.get("JIEJIAN_VAR_DIR")
    if var_dir:
        return RuntimePaths(Path(var_dir)).temp / "process-gates"
    # 直接边界测试可能没有完整启动环境；生产进程始终由启动器注入 JIEJIAN_VAR_DIR。
    return cwd / ".jiejian-process-gates"


def run_python_module(
    source: Mapping[str, str],
    module: str,
    *arguments: str,
    cwd: Path,
    timeout_seconds: float,
    secret_names: Sequence[str] = (),
    extra_environment: Mapping[str, str] | None = None,
    allowed_extra_names: Sequence[str] = (),
    python_executable: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """运行一个需要捕获文本输出的短命模块，并在所有出口回收整棵进程树。"""

    process = spawn_python_module(
        source,
        module,
        *arguments,
        secret_names=secret_names,
        extra_environment=extra_environment,
        allowed_extra_names=allowed_extra_names,
        cwd=cwd,
        python_executable=python_executable,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        close_fds=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        release_process_tree(process)
        return subprocess.CompletedProcess(
            args=process.args,
            returncode=process.returncode,
            stdout=stdout,
            stderr=stderr,
        )
    except subprocess.TimeoutExpired:
        terminate_process_tree(process, 2.0)
        raise
