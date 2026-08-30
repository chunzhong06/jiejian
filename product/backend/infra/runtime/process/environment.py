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
#   只传播固定角色白名单与显式业务 secret；调用方不得借附加变量改写受控身份。
#
# 调用链
#   Worker / Runner / Recording / Observer / Sample / Artifact / Selector → 本模块 → process tree
# =============================================================================

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Callable
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any
from uuid import uuid4

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.infra.runtime.process.tree import ProcessTreeController, controller_for, release_process_tree, spawn_managed_process, terminate_process_tree


class ProcessEnvironmentRole(StrEnum):
    """产品 Python 子进程的固定最小环境角色。"""

    WORKER = "WORKER"
    RUNNER = "RUNNER"
    RECORDING = "RECORDING"
    IDENTITY_PREPARATION = "IDENTITY_PREPARATION"
    OBSERVER = "OBSERVER"
    SAMPLE = "SAMPLE"
    ARTIFACT_SCAN = "ARTIFACT_SCAN"
    ONBOARDING_SELECTOR = "ONBOARDING_SELECTOR"


@dataclass(frozen=True, slots=True)
class _RoleEnvironmentPolicy:
    source_names: frozenset[str]
    extra_names: frozenset[str]
    allows_secrets: bool


_COMMON_SOURCE_NAMES = frozenset(
    {
        "COMSPEC",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "JIEJIAN_PYTHON_EXECUTABLE",
        "JIEJIAN_PYTHON_ENVIRONMENT_PATH",
        "JIEJIAN_PYTHON_ENVIRONMENT_TYPE",
        "JIEJIAN_PROJECT_ROOT",
        "JIEJIAN_RELEASE_ROOT",
        "JIEJIAN_RUNTIME_FINGERPRINT",
        "JIEJIAN_RUNTIME_MODE",
        "JIEJIAN_VAR_DIR",
    }
)


def _policy(
    *,
    source_names: frozenset[str] = frozenset(),
    extra_names: frozenset[str] = frozenset(),
    allows_secrets: bool,
) -> _RoleEnvironmentPolicy:
    return _RoleEnvironmentPolicy(
        source_names=source_names,
        extra_names=extra_names,
        allows_secrets=allows_secrets,
    )


_ROLE_POLICIES = MappingProxyType(
    {
        ProcessEnvironmentRole.WORKER: _policy(
            source_names=frozenset(
                {
                    "JIEJIAN_CONTROL_ORIGIN",
                    "JIEJIAN_SERVE_LOCK_PATH",
                    "JIEJIAN_SERVE_OWNER_TOKEN",
                    # Worker 是 Recording 的受信启动中介，必须保留非秘密浏览器运行时根路径。
                    "PLAYWRIGHT_BROWSERS_PATH",
                }
            ),
            allows_secrets=True,
        ),
        ProcessEnvironmentRole.RUNNER: _policy(
            source_names=frozenset({"JIEJIAN_CONTROL_ORIGIN"}),
            allows_secrets=True,
        ),
        ProcessEnvironmentRole.RECORDING: _policy(
            source_names=frozenset({"PLAYWRIGHT_BROWSERS_PATH"}),
            extra_names=frozenset(
                {
                    "JIEJIAN_RECORDING_CANCEL_FILE",
                    "JIEJIAN_RECORDING_ATTEMPT_DIR",
                }
            ),
            allows_secrets=True,
        ),
        ProcessEnvironmentRole.IDENTITY_PREPARATION: _policy(
            source_names=frozenset({"PLAYWRIGHT_BROWSERS_PATH"}),
            extra_names=frozenset({"JIEJIAN_IDENTITY_PREPARATION_DIR"}),
            allows_secrets=False,
        ),
        ProcessEnvironmentRole.OBSERVER: _policy(
            extra_names=frozenset({"JIEJIAN_ATTEMPT_DIR"}),
            allows_secrets=True,
        ),
        ProcessEnvironmentRole.SAMPLE: _policy(allows_secrets=True),
        ProcessEnvironmentRole.ARTIFACT_SCAN: _policy(allows_secrets=False),
        ProcessEnvironmentRole.ONBOARDING_SELECTOR: _policy(
            extra_names=frozenset(
                {
                    "ALLUSERSPROFILE",
                    "APPDATA",
                    "HOMEDRIVE",
                    "HOMEPATH",
                    "PROGRAMDATA",
                    "PUBLIC",
                    "SYSTEMDRIVE",
                }
            ),
            allows_secrets=False,
        ),
    }
)


_COMMON_IDENTITY_NAMES = frozenset(
    {
        "JIEJIAN_PYTHON_EXECUTABLE",
        "JIEJIAN_PYTHON_ENVIRONMENT_PATH",
        "JIEJIAN_PYTHON_ENVIRONMENT_TYPE",
        "JIEJIAN_RUNTIME_FINGERPRINT",
        "JIEJIAN_RUNTIME_MODE",
        "JIEJIAN_VAR_DIR",
    }
)
_RUNTIME_IDENTITY_NAMES = MappingProxyType(
    {
        "development": frozenset({"JIEJIAN_PROJECT_ROOT"}),
        "portable": frozenset(
            {
                "JIEJIAN_RELEASE_ROOT",
                "JIEJIAN_PLAYWRIGHT_EXECUTABLE",
                "PLAYWRIGHT_BROWSERS_PATH",
            }
        ),
    }
)
_ALL_IDENTITY_NAMES = _COMMON_IDENTITY_NAMES | frozenset().union(
    *_RUNTIME_IDENTITY_NAMES.values()
)


_MAIN_PROCESS_ONLY_NAMES = frozenset(
    {
        "JIEJIAN_FRONTEND_BUILD_STATE",
        "JIEJIAN_FRONTEND_DEPENDENCIES",
        "JIEJIAN_FRONTEND_DIST",
        "JIEJIAN_NODE_EXECUTABLE",
        "JIEJIAN_NODE_VERSION",
        "JIEJIAN_PNPM_EXECUTABLE",
        "JIEJIAN_PNPM_VERSION",
        "JIEJIAN_TOOLCHAIN_MANIFEST",
        "JIEJIAN_UV_EXECUTABLE",
        "JIEJIAN_UV_VERSION",
        "UV_CACHE_DIR",
        "UV_PROJECT_ENVIRONMENT",
        "UV_PYTHON_INSTALL_DIR",
    }
)
_FORCED_ENVIRONMENT_NAMES = frozenset(
    {
        "PATH",
        "TEMP",
        "TMP",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONHOME",
        "PYTHONIOENCODING",
        "PYTHONNOUSERSITE",
        "PYTHONPATH",
        "PYTHONUTF8",
    }
)
_ROLE_CONTROLLED_NAMES = frozenset().union(
    *(policy.source_names | policy.extra_names for policy in _ROLE_POLICIES.values())
)
_CONTROLLED_NAME_CASEFOLDS = frozenset(
    name.casefold()
    for name in (
        _COMMON_SOURCE_NAMES
        | _MAIN_PROCESS_ONLY_NAMES
        | _FORCED_ENVIRONMENT_NAMES
        | _ROLE_CONTROLLED_NAMES
    )
)
_ENVIRONMENT_NAME_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_FAILURE_REASON_BY_MESSAGE = MappingProxyType(
    {
        "Python 子进程角色无效": "PROCESS_ROLE_INVALID",
        "Python 子进程秘密引用无效": "SECRET_REFERENCE_INVALID",
        "Python 子进程秘密引用与受控环境变量冲突": "SECRET_REFERENCE_INVALID",
        "当前 Python 子进程角色不允许秘密引用": "SECRET_REFERENCE_INVALID",
        "Python 子进程环境变量无效": "ENVIRONMENT_VALUE_INVALID",
        "Python 子进程环境变量名称冲突": "ENVIRONMENT_NAME_CONFLICT",
        "Python 子进程缺少共同运行身份": "COMMON_IDENTITY_MISSING",
        "当前 Python 与界鉴启动阶段确认的解释器不一致": "PYTHON_IDENTITY_MISMATCH",
        "Python 子进程工作目录不存在": "WORKING_DIRECTORY_MISSING",
        "Python 子进程附加环境变量无效": "EXTRA_ENVIRONMENT_REJECTED",
        "Python 子进程附加环境变量越界": "EXTRA_ENVIRONMENT_REJECTED",
        "Python 子进程不得替换启动阶段确认的解释器": "PYTHON_IDENTITY_MISMATCH",
    }
)


def _coerce_role(role: ProcessEnvironmentRole | str) -> ProcessEnvironmentRole:
    try:
        return ProcessEnvironmentRole(role)
    except (ValueError, TypeError):
        raise JiejianError(
            ErrorCode.RUNTIME_ENVIRONMENT_INVALID,
            "Python 子进程角色无效",
        ) from None


def _role_policy(role: ProcessEnvironmentRole | str) -> _RoleEnvironmentPolicy:
    return _ROLE_POLICIES[_coerce_role(role)]


def _validate_secret_names(
    role: ProcessEnvironmentRole,
    secret_names: Sequence[str],
) -> tuple[str, ...]:
    """验证业务 secret 引用，禁止其借名覆盖运行身份或其他角色变量。"""

    policy = _role_policy(role)
    names: list[str] = []
    seen: set[str] = set()
    for name in secret_names:
        if not isinstance(name, str) or _ENVIRONMENT_NAME_PATTERN.fullmatch(name) is None:
            raise JiejianError(
                ErrorCode.RUNTIME_ENVIRONMENT_INVALID,
                "Python 子进程秘密引用无效",
            )
        folded = name.casefold()
        if folded in _CONTROLLED_NAME_CASEFOLDS:
            raise JiejianError(
                ErrorCode.RUNTIME_ENVIRONMENT_INVALID,
                "Python 子进程秘密引用与受控环境变量冲突",
                details={"name": name},
            )
        if folded not in seen:
            seen.add(folded)
            names.append(name)
    if names and not policy.allows_secrets:
        raise JiejianError(
            ErrorCode.RUNTIME_ENVIRONMENT_INVALID,
            "当前 Python 子进程角色不允许秘密引用",
        )
    return tuple(names)


def _casefold_environment(source: Mapping[str, str]) -> dict[str, tuple[str, str]]:
    """按 Windows 环境变量语义建立索引，并拒绝大小写歧义输入。"""

    by_casefold: dict[str, tuple[str, str]] = {}
    for key, value in source.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise JiejianError(
                ErrorCode.RUNTIME_ENVIRONMENT_INVALID,
                "Python 子进程环境变量无效",
            )
        folded = key.casefold()
        previous = by_casefold.get(folded)
        if previous is not None and previous[0] != key:
            raise JiejianError(
                ErrorCode.RUNTIME_ENVIRONMENT_INVALID,
                "Python 子进程环境变量名称冲突",
                details={"names": sorted((previous[0], key))},
            )
        by_casefold[folded] = (key, value)
    return by_casefold


def process_environment_failure_summary(error: JiejianError) -> dict[str, object]:
    """把 Popen 前的环境拒绝投影为无值、无路径的稳定诊断。"""

    if error.code != ErrorCode.RUNTIME_ENVIRONMENT_INVALID.value:
        return {}
    payload = error.to_dict()
    message = payload.get("message")
    reason = _FAILURE_REASON_BY_MESSAGE.get(
        message if isinstance(message, str) else "",
        "RUNTIME_ENVIRONMENT_REJECTED",
    )
    summary: dict[str, object] = {"reason": reason}
    if reason != "COMMON_IDENTITY_MISSING":
        return summary
    details = payload.get("details")
    missing = details.get("missing") if isinstance(details, Mapping) else None
    if isinstance(missing, (list, tuple)):
        names = sorted(
            name
            for name in missing
            if isinstance(name, str) and name in _ALL_IDENTITY_NAMES
        )
        if names:
            summary["missing_names"] = names
    return summary


def minimal_process_environment(
    source: Mapping[str, str],
    *,
    role: ProcessEnvironmentRole,
    secret_names: Sequence[str] = (),
) -> dict[str, str]:
    """按固定角色只传递共同身份、角色变量和明确引用的秘密。"""

    role = _coerce_role(role)
    policy = _role_policy(role)
    names = _validate_secret_names(role, secret_names)
    by_casefold = _casefold_environment(source)
    runtime_mode_entry = by_casefold.get("JIEJIAN_RUNTIME_MODE".casefold())
    runtime_mode = runtime_mode_entry[1].strip().lower() if runtime_mode_entry else ""
    required_identity_names = _COMMON_IDENTITY_NAMES | _RUNTIME_IDENTITY_NAMES.get(
        runtime_mode, frozenset()
    )
    missing_identity = sorted(
        name
        for name in required_identity_names
        if not (by_casefold.get(name.casefold()) and by_casefold[name.casefold()][1])
    )
    if missing_identity:
        raise JiejianError(
            ErrorCode.RUNTIME_ENVIRONMENT_INVALID,
            "Python 子进程缺少共同运行身份",
            details={"missing": missing_identity},
        )
    selected_names = tuple(
        dict.fromkeys(
            (*_COMMON_SOURCE_NAMES, *required_identity_names, *policy.source_names, *names)
        )
    )
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
    configured_entry = _casefold_environment(source).get(
        "JIEJIAN_PYTHON_EXECUTABLE".casefold()
    )
    configured = configured_entry[1] if configured_entry is not None else None
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
    role: ProcessEnvironmentRole,
    secret_names: Sequence[str] = (),
    extra_environment: Mapping[str, str] | None = None,
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
    role = _coerce_role(role)
    policy = _role_policy(role)
    environment = minimal_process_environment(
        source,
        role=role,
        secret_names=secret_names,
    )
    allowed_extras = {name.casefold(): name for name in policy.extra_names}
    seen_extras: set[str] = set()
    for name, value in (extra_environment or {}).items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise JiejianError(
                ErrorCode.RUNTIME_ENVIRONMENT_INVALID,
                "Python 子进程附加环境变量无效",
            )
        folded = name.casefold()
        canonical_name = allowed_extras.get(folded)
        if canonical_name is None or folded in seen_extras:
            raise JiejianError(
                ErrorCode.RUNTIME_ENVIRONMENT_INVALID,
                "Python 子进程附加环境变量越界",
                details={"name": name},
            )
        seen_extras.add(folded)
        if value:
            environment[canonical_name] = value

    executable = confirmed_python_executable(environment)
    if python_executable is not None:
        # 显式参数只能验证调用边界，不能成为绕过启动身份的第二解释器来源。
        requested = Path(python_executable).resolve()
        if requested != Path(executable) or not requested.is_file():
            raise JiejianError(
                ErrorCode.RUNTIME_ENVIRONMENT_INVALID,
                "Python 子进程不得替换启动阶段确认的解释器",
                details={"expected": executable, "requested": str(requested)},
            )
    gate_root = _process_gate_root(environment, working_directory)
    gate_root.mkdir(parents=True, exist_ok=True)
    gate_path = gate_root / f"gate-{uuid4().hex}.ready"
    command = [
        executable,
        "-B",
        "-m",
        "product.backend.infra.runtime.process.bootstrap",
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
        return RuntimePaths(Path(var_dir)).process_gates
    # 直接边界测试可能没有完整启动环境；生产进程始终由启动器注入 JIEJIAN_VAR_DIR。
    return cwd / ".jiejian-process-gates"


def run_python_module(
    source: Mapping[str, str],
    module: str,
    *arguments: str,
    role: ProcessEnvironmentRole,
    cwd: Path,
    timeout_seconds: float,
    secret_names: Sequence[str] = (),
    extra_environment: Mapping[str, str] | None = None,
    python_executable: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """运行一个需要捕获文本输出的短命模块，并在所有出口回收整棵进程树。"""

    process = spawn_python_module(
        source,
        module,
        *arguments,
        role=role,
        secret_names=secret_names,
        extra_environment=extra_environment,
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
