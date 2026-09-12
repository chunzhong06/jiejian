# 自动 L5 总编排：从真实 start.cmd 启动产品并验证 GUI、Sample、Recording、Verification 与安全退出。

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright
from product.backend.core.errors import JiejianError
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.infra.runtime.process.lock import lock_is_available
from product.backend.infra.runtime.process.tree import (
    process_tree_has_exited,
    release_process_tree,
    spawn_managed_process,
    terminate_process_tree,
)
from product.backend.infra.runtime.process.identity import require_python_environment


PROJECT_KEY = "campus-digital-museum"
RESOURCE_ID = "campus-digital-museum-package"
EXPORT_ACTION_KEY = "POST /api/projects/{project_id}/exports"
VIEW_ACTION_KEY = "GET /api/projects/{project_id}/collaboration"
CONTROL_PORT = 8765
PHASE_TITLES = {
    1: "启动隔离实例", 2: "准备官方示例", 3: "确认权限与准备材料", 4: "问题版检查",
    5: "观察不足的新检查", 6: "原题修复与新检查", 7: "结果与历史证据核对", 8: "退出与资源清理",
}

ROLE_LABELS = {
    "project_owner": "项目负责人",
    "member": "普通成员",
}
SOURCE_LABELS = (
    ("OWNER_API", "目标业务状态", "SUPPORTING"),
    ("READ_ONLY_SQLITE", "只读数据库", "SUPPORTING"),
    ("STRUCTURED_AUDIT_LOG", "结构化审计记录", "DIAGNOSIS_REQUIRED"),
    ("ASYNC_TASK_STATUS", "后台任务", "SUPPORTING"),
    ("AZURE_QUEUE_PEEK", "消息通道", "SUPPORTING"),
    ("AZURE_BLOB_OBJECT", "最终对象/文件", "VERDICT_REQUIRED"),
)
SOURCE_TYPES = {item[0] for item in SOURCE_LABELS}
_MAX_SOURCE_RECEIPT_BYTES = 1_048_576
_FINGERPRINT = re.compile(r"[0-9a-f]{64}\Z")


class SampleTestError(RuntimeError):
    """只承载无秘密的公开验收失败摘要。"""


@dataclass(frozen=True, slots=True)
class SourceRuntime:
    """从受控回执复核出的本轮解释器身份与浏览器输入。"""

    environment: dict[str, str]
    playwright_executable: Path
    frontend_dir: Path


@dataclass(slots=True)
class HarnessState:
    """保存失败清理所需的最小公开身份与当前验收步骤。"""

    stage: int = 0
    active_run_id: str | None = None
    active_run_job_id: str | None = None
    sample_started: bool = False
    product_ready: bool = False


def _required_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise SampleTestError(f"source receipt 缺少有效的 {label}")
    return value


def _required_text(source: Mapping[str, object], name: str) -> str:
    value = source.get(name)
    if not isinstance(value, str) or not value:
        raise SampleTestError(f"source receipt 缺少有效的 {name}")
    return value


def _load_source_runtime(
    receipt_path: Path,
    root: Path,
    var_dir: Path,
) -> SourceRuntime:
    """只信任真实 start.cmd 在本轮隔离目录中生成的 source receipt。"""

    try:
        if receipt_path.stat().st_size > _MAX_SOURCE_RECEIPT_BYTES:
            raise SampleTestError("source receipt 超出大小限制")
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except SampleTestError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise SampleTestError("source receipt 不可读取或格式无效") from None
    receipt = _required_mapping(payload, "root")
    python = _required_mapping(receipt.get("python"), "python")
    playwright = _required_mapping(receipt.get("playwright"), "playwright")
    frontend = _required_mapping(receipt.get("frontend"), "frontend")
    if _required_text(receipt, "schema_version") != "1":
        raise SampleTestError("source receipt 版本不受支持")
    executable = Path(_required_text(python, "executable")).resolve()
    environment_path = Path(_required_text(python, "environment_path")).resolve()
    fingerprint = _required_text(python, "runtime_fingerprint")
    playwright_executable = Path(_required_text(playwright, "executable")).resolve()
    browsers_path = Path(_required_text(playwright, "browsers_path")).resolve()
    frontend_dir = Path(_required_text(frontend, "dist")).resolve()
    if (
        Path(_required_text(receipt, "project_root")).resolve() != root
        or Path(_required_text(receipt, "var_dir")).resolve() != var_dir
        or executable != Path(sys.executable).resolve()
        or environment_path != Path(sys.prefix).resolve()
        or _required_text(python, "environment_type") != "conda"
        or _required_text(receipt, "runtime_mode") != "development"
        or _FINGERPRINT.fullmatch(fingerprint) is None
        or not (frontend_dir / "index.html").is_file()
        or not playwright_executable.is_file()
        or not browsers_path.is_dir()
    ):
        raise SampleTestError("source receipt 与当前受控运行输入不一致")
    system_values = {
        name: os.environ[name]
        for name in ("COMSPEC", "PATHEXT", "SYSTEMROOT", "WINDIR")
        if os.environ.get(name)
    }
    temporary = RuntimePaths(var_dir).temp
    temporary.mkdir(parents=True, exist_ok=True)
    system_root = system_values.get("SYSTEMROOT") or system_values.get("WINDIR")
    path_entries = [str(executable.parent)]
    if system_root:
        path_entries.append(str(Path(system_root) / "System32"))
    environment = {
        **system_values,
        "JIEJIAN_PYTHON_EXECUTABLE": str(executable),
        "JIEJIAN_PYTHON_ENVIRONMENT_PATH": str(environment_path),
        "JIEJIAN_PYTHON_ENVIRONMENT_TYPE": "conda",
        "JIEJIAN_PROJECT_ROOT": str(root),
        "JIEJIAN_RUNTIME_FINGERPRINT": fingerprint,
        "JIEJIAN_RUNTIME_MODE": "development",
        "JIEJIAN_VAR_DIR": str(var_dir),
        "JIEJIAN_FRONTEND_DIST": str(frontend_dir),
        "JIEJIAN_PLAYWRIGHT_EXECUTABLE": str(playwright_executable),
        "PLAYWRIGHT_BROWSERS_PATH": str(browsers_path),
        "PATH": os.pathsep.join(dict.fromkeys(path_entries)),
        "TEMP": str(temporary),
        "TMP": str(temporary),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    try:
        require_python_environment(environment)
    except JiejianError as exc:
        raise SampleTestError(
            f"source receipt 运行身份复核失败: {exc.code}"
        ) from None
    return SourceRuntime(
        environment=environment,
        playwright_executable=playwright_executable,
        frontend_dir=frontend_dir,
    )


class ApiClient:
    """访问单个 loopback 控制面的严格 JSON envelope 客户端。"""

    def __init__(self, origin: str) -> None:
        self.origin = origin.rstrip("/")
        self._page: Page | None = None

    def bind_page(self, page: Page) -> None:
        """把后续业务请求绑定到已由根页面取得的 HttpOnly 控制会话。"""

        self._page = page

    def call(
        self,
        method: str,
        path: str,
        body: dict[str, object] | None = None,
        *,
        accepted: tuple[int, ...] = (200,),
    ) -> Any:
        if self._page is not None:
            result = self._page.evaluate(
                """async ({method, path, body}) => {
                    const options = {method, headers: {Accept: 'application/json'}};
                    if (body !== null) {
                        options.headers['Content-Type'] = 'application/json';
                        options.body = JSON.stringify(body);
                    }
                    const response = await fetch(path, options);
                    return {status: response.status, text: await response.text()};
                }""",
                {"method": method, "path": path, "body": body},
            )
            status = int(result["status"])
            raw = str(result["text"]).encode("utf-8")
        else:
            encoded = None
            headers = {"Accept": "application/json"}
            if body is not None:
                encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
                headers["Content-Type"] = "application/json"
            request = Request(
                self.origin + path,
                data=encoded,
                headers=headers,
                method=method,
            )
            try:
                with urlopen(request, timeout=20) as response:
                    status = response.status
                    raw = response.read()
            except HTTPError as exc:
                raw = exc.read()
                raise SampleTestError(
                    f"{method} {path} 返回 {exc.code}: {_public_error(raw)}"
                ) from None
            except (OSError, URLError) as exc:
                raise SampleTestError(f"{method} {path} 无法访问: {type(exc).__name__}") from None
        if status not in accepted:
            raise SampleTestError(
                f"{method} {path} 返回非预期状态 {status}: {_public_error(raw)}"
            )
        try:
            payload = json.loads(raw)
        except (UnicodeError, json.JSONDecodeError):
            raise SampleTestError(f"{method} {path} 未返回有效 JSON") from None
        if not isinstance(payload, dict) or payload.get("schema_version") != "1" or "data" not in payload:
            raise SampleTestError(f"{method} {path} 返回的 envelope 无效")
        return payload["data"]

    def raw(self, path: str) -> bytes:
        if self._page is not None:
            result = self._page.evaluate(
                """async (path) => {
                    const response = await fetch(path, {headers: {Accept: '*/*'}});
                    return {status: response.status, text: await response.text()};
                }""",
                path,
            )
            if int(result["status"]) != 200:
                raise SampleTestError(f"GET {path} 返回非预期状态 {result['status']}")
            return str(result["text"]).encode("utf-8")
        try:
            with urlopen(self.origin + path, timeout=20) as response:
                return response.read()
        except (HTTPError, OSError, URLError) as exc:
            raise SampleTestError(f"GET {path} 无法读取: {type(exc).__name__}") from None

    def readiness(self) -> dict[str, object]:
        """读取不使用业务 envelope 的标准就绪探针。"""

        raw = self.raw("/ready")
        try:
            payload = json.loads(raw)
        except (UnicodeError, json.JSONDecodeError):
            raise SampleTestError("GET /ready 未返回有效 JSON") from None
        if not isinstance(payload, dict) or payload.get("schema_version") != "1":
            raise SampleTestError("GET /ready 返回格式无效")
        return payload


def _public_error(raw: bytes) -> str:
    try:
        payload = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError):
        return "响应无法解析"
    if not isinstance(payload, dict):
        return "响应格式无效"
    detail = payload.get("detail")
    if isinstance(detail, dict):
        return str(detail.get("code") or "请求失败")
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("code") or "请求失败")
    return str(payload.get("code") or "请求失败")


def _phase(state: HarnessState, number: int) -> None:
    state.stage = number
    print(f"[{number}/{len(PHASE_TITLES)}] {PHASE_TITLES[number]}", flush=True)


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.2)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def _wait_for(
    read: Callable[[], Any],
    accept: Callable[[Any], bool],
    *,
    timeout: float,
    label: str,
) -> Any:
    deadline = time.monotonic() + timeout
    latest: Any = None
    while time.monotonic() < deadline:
        try:
            latest = read()
            if accept(latest):
                return latest
        except SampleTestError:
            pass
        time.sleep(0.2)
    summary = latest if isinstance(latest, (str, int, float, bool, type(None))) else type(latest).__name__
    raise SampleTestError(f"等待{label}超时，最后状态: {summary}")


def _start_product(
    root: Path,
    var_dir: Path,
) -> tuple[subprocess.Popen[bytes], object]:
    """通过真实 start.cmd 启动本轮拥有的产品进程树。"""

    log_path = var_dir / "logs" / "sample-test-start.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("wb")
    command_shell = os.environ.get("COMSPEC")
    if not command_shell or not Path(command_shell).is_file():
        log.close()
        raise SampleTestError("L5_COMMAND_SHELL_UNAVAILABLE")
    command = [
        command_shell,
        "/d",
        "/s",
        "/c",
        "call",
        str(root / "start.cmd"),
        "-Mode",
        "Gui",
        "-VarDir",
        str(var_dir),
    ]
    try:
        process = spawn_managed_process(
            command,
            cwd=root,
            env=os.environ.copy(),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            tree_name=f"jiejian-sample-test-{uuid4().hex}",
        )
    except Exception:
        log.close()
        raise
    return process, log


def _wait_source_prepare(
    receipt_path: Path,
    process: subprocess.Popen[bytes],
    *,
    timeout: float,
) -> None:
    """先等待本轮 source receipt，区分准备超时与控制面未就绪。"""

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        return_code = process.poll()
        if return_code is not None:
            raise SampleTestError(f"START_CMD_EXITED_DURING_PREPARE:{return_code}")
        if receipt_path.is_file():
            return
        time.sleep(0.2)
    raise SampleTestError("L5_SOURCE_PREPARE_TIMEOUT")


def _wait_product_ready(
    client: ApiClient,
    process: subprocess.Popen[bytes],
    *,
    timeout: float,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        return_code = process.poll()
        if return_code is not None:
            raise SampleTestError(f"START_CMD_EXITED_AFTER_PREPARE:{return_code}")
        try:
            ready = client.readiness()
        except SampleTestError:
            time.sleep(0.2)
            continue
        if ready.get("status") == "ready" and ready.get("worker") == "running":
            return ready
        time.sleep(0.2)
    raise SampleTestError("L5_CONTROL_READY_TIMEOUT")


def _wait_for_published_result(client, run_id, run_job_id):
    from .current_api import wait_published
    return wait_published(client, run_id, run_job_id)


def _load_evidence(client, run_id):
    from .current_api import read_result
    result = read_result(client, run_id)
    return result["evidence_index"], result["evidence"]


def _write_summary(audit_dir: Path, payload: dict[str, object]) -> None:
    audit_dir.mkdir(parents=True, exist_ok=True)
    path = audit_dir / "sample-test-summary.json"
    temporary = path.with_suffix(f".{uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _failure_identity(error: Exception) -> tuple[str, str]:
    """把主错误压缩成稳定、无秘密的审计字段。"""

    if isinstance(error, SampleTestError):
        summary = str(error)
        token = summary.split(":", 1)[0]
        code = token if re.fullmatch(r"[A-Z][A-Z0-9_]+", token) else type(error).__name__.upper()
        return code, summary[:512]
    if isinstance(error, PlaywrightError):
        return "PLAYWRIGHT_ERROR", "Playwright 自动化边界失败"
    return type(error).__name__.upper(), "自动 L5 出现未分类失败"


def _cleanup_after_failure(
    client: ApiClient,
    state: HarnessState,
    identities: Mapping[str, str],
) -> dict[str, object]:
    """按公开 API 收口身份、Sample 和控制面，不覆盖首个失败。"""

    report: dict[str, object] = {"actions": []}
    actions = report["actions"]
    assert isinstance(actions, list)
    if not state.product_ready:
        report.update(
            {
                "state_closed": True,
                "shutdown_requested": False,
            }
        )
        return report
    report["state_closed"] = True
    if state.active_run_job_id is not None:
        try:
            client.call("POST", f"/api/jobs/{state.active_run_job_id}/cancel")
            actions.append("check.cancel")
            _wait_for(lambda: client.call("GET", f"/api/runs/{state.active_run_id}"),
                lambda item: (item.get("job") or {}).get("state") in {"SUCCEEDED", "FAILED", "CANCELLED"},
                timeout=30, label="取消本次检查")
        except Exception as error:
            report["check_cleanup_error"] = type(error).__name__
            report["state_closed"] = False
    for identity_id in identities.values():
        try:
            client.call(
                "POST",
                f"/api/test-identities/{identity_id}/reset",
                {"schema_version": "1"},
            )
            actions.append("identity.reset")
        except Exception as error:
            report.setdefault("identity_cleanup_errors", []).append(type(error).__name__)
    if state.sample_started:
        try:
            client.call("POST", "/api/experience/official-sample/stop", {"schema_version": "1"})
            actions.append("official-sample.stop")
        except Exception as error:
            report["sample_cleanup_error"] = type(error).__name__
    try:
        client.call("POST", "/api/system/shutdown", {"schema_version": "1"}, accepted=(202,))
        actions.append("system.shutdown")
        report["shutdown_requested"] = True
    except Exception as error:
        report["shutdown_requested"] = False
        report["shutdown_error"] = type(error).__name__
    return report


def _write_failure(
    audit_dir: Path,
    error: Exception,
    state: HarnessState,
    cleanup: Mapping[str, object],
    *,
    control_closed: bool,
    sample_closed: bool | None,
    process_tree_closed: bool,
) -> None:
    code, summary = _failure_identity(error)
    screenshots = [path.relative_to(audit_dir).as_posix() for path in sorted(audit_dir.glob("*.png"))]
    _write_summary(
        audit_dir,
        {
            "schema_version": "1",
            "l5_stage": state.stage,
            "failure_code": code,
            "primary_failure": summary,
            "active_run_id": state.active_run_id,
            "active_run_job_id": state.active_run_job_id,
            "cleanup": dict(cleanup),
            "resources": {
                "control_port_closed": control_closed,
                "sample_port_closed": sample_closed,
                "owned_process_tree_closed": process_tree_closed,
            },
            "logs": ["../../logs/sample-test-start.log"],
            "screenshots": screenshots,
        },
    )
    (audit_dir / "sample-test-summary.json").replace(audit_dir / "failure.json")


def _runtime_locks_released(var_dir: Path) -> bool:
    """按系统锁可重新获取证明释放；诊断锁文件允许继续保留。"""

    runtime_paths = RuntimePaths(var_dir)
    lock_paths = (
        runtime_paths.locks / "serve.lock",
        *sorted(runtime_paths.worker_runtime.glob("*.lock")),
    )
    try:
        return all(
            lock_is_available(path)
            for path in lock_paths
            if path.exists()
        )
    except OSError:
        return False


def _shutdown_owned_runtime(
    client: ApiClient,
    state: HarnessState,
    identities: Mapping[str, str],
    browser: object,
    playwright: object,
    process: subprocess.Popen[bytes],
    var_dir: Path,
    sample_port: int | None,
    shutdown_action=None,
) -> None:
    """通过正式 API 关闭产品资源，并证明本轮端口、进程树和锁均已收口。"""

    for identity_id in identities.values():
        reset = client.call(
            "POST",
            f"/api/test-identities/{identity_id}/reset",
            {"schema_version": "1"},
        )
        if reset.get("status") != "NOT_PREPARED":
            raise SampleTestError("测试账号秘密引用没有完成受控清理")
    client.call("POST", "/api/experience/official-sample/stop", {"schema_version": "1"})
    state.sample_started = False
    if shutdown_action is None:
        client.call("POST", "/api/system/shutdown", {"schema_version": "1"}, accepted=(202,))
    else:
        shutdown_action()
    browser.close()
    playwright.stop()
    process.wait(timeout=30)
    if process.returncode != 0:
        raise SampleTestError(f"控制面安全关闭返回 {process.returncode}")
    if not process_tree_has_exited(process):
        raise SampleTestError("L5_OWNED_PROCESS_TREE_NOT_CLOSED")
    release_process_tree(process, timeout=5)
    if _port_open(CONTROL_PORT) or (sample_port is not None and _port_open(sample_port)):
        raise SampleTestError("安全关闭后仍有受控端口占用")
    if not _runtime_locks_released(var_dir):
        raise SampleTestError("L5_RUNTIME_LOCK_NOT_RELEASED")


def run(
    root: Path,
    var_dir: Path,
    *,
    stop_after_setup: bool = False,
    verify_workspace_ui: bool = False,
) -> None:
    root = root.resolve()
    var_dir = var_dir.resolve()
    if any(var_dir.iterdir()):
        raise SampleTestError("sample-test 必须从全新的空运行目录开始")
    audit_dir = var_dir / "audit" / "sample-test"
    audit_dir.mkdir(parents=True)
    state = HarnessState(stage=1)
    if _port_open(CONTROL_PORT):
        occupied = SampleTestError("L5_CONTROL_PORT_OCCUPIED")
        _write_failure(
            audit_dir,
            occupied,
            state,
            {
                "actions": [],
                "before": None,
                "after": None,
                "state_closed": True,
                "shutdown_requested": False,
            },
            control_closed=False,
            sample_closed=None,
            process_tree_closed=True,
        )
        raise occupied
    process: subprocess.Popen[bytes] | None = None
    log: object | None = None
    browser = None
    playwright = None
    sample_port: int | None = None
    source_runtime: SourceRuntime | None = None
    client = ApiClient(f"http://127.0.0.1:{CONTROL_PORT}")
    identities: dict[str, str] = {}
    project_id = ""
    primary_failure: Exception | None = None
    failure_cleanup: dict[str, object] = {}
    try:
        _phase(state, 1)
        process, log = _start_product(root, var_dir)
        receipt_path = var_dir / "runtime" / "source" / "receipt.json"
        _wait_source_prepare(
            receipt_path,
            process,
            timeout=600,
        )
        source_runtime = _load_source_runtime(
            receipt_path,
            root,
            var_dir,
        )
        _wait_product_ready(
            client,
            process,
            timeout=90,
        )
        state.product_ready = True
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=str(source_runtime.playwright_executable),
        )
        page = browser.new_page(viewport={"width": 2560, "height": 1440})
        client.bind_page(page)

        from .current_api import prepare_current, project_run_ids, run_sequence
        from .current_gui import CurrentGui
        gui = CurrentGui(page, client, audit_dir)
        def checkpoint(event, payload):
            if event == "limited-ready":
                _phase(state, 5)
            elif event == "fixed-ready":
                _phase(state, 6)
            gui.checkpoint(event, payload)
        _phase(state, 2)
        page.goto(client.origin, wait_until="networkidle")
        experience = gui.start()
        state.sample_started = True
        project_id = str(experience["project_id"])
        sample_port = int(str(experience["origin"]).rsplit(":", 1)[1])
        if not experience.get("active") or experience.get("scenario_version") != "VULNERABLE" or project_run_ids(client, project_id):
            raise SampleTestError("SAMPLE_NEW_INSTANCE_INVALID")
        _phase(state, 3)
        prepare_current(client, project_id, initial=True, gui=gui)
        prepared_identities = client.call("GET", f"/api/projects/{project_id}/test-identities")
        identities = {str(index): str(item["identity_id"]) for index, item in enumerate(prepared_identities)}
        if stop_after_setup:
            runs = []
        else:
            _phase(state, 4)
            runs = run_sequence(client, project_id, state, checkpoint=checkpoint, gui=gui)
        _phase(state, 7)
        page.goto(client.origin + "/#/tests", wait_until="networkidle")
        if not stop_after_setup:
            checkpoint("evidence-and-repair", {"project_id": project_id, "runs": runs})
        _phase(state, 8)
        _shutdown_owned_runtime(client, state, identities, browser, playwright, process, var_dir, sample_port, shutdown_action=gui.shutdown)
        browser = None
        playwright = None
        process = None
        state.product_ready = False
        required_gui = {"start", "human-approve", "prepare", "exit"} | (set() if stop_after_setup else {"submit-check", "problem-result", "limited-result", "fixed-result", "evidence-and-repair"})
        gui_complete = required_gui.issubset({item["event"] for item in gui.records if item.get("status") == "PASSED"})
        _write_summary(audit_dir, {"schema_version": "1", "project_id": project_id,
            "scenario_versions": [] if stop_after_setup else ["VULNERABLE", "EVIDENCE_LIMITED", "FIXED"],
            "runs": [{"run_id": item["run_id"], "verdict": item["story"]["verdict"]} for item in runs],
            "read_projections": ["ResultStory", "Evidence", "RunHistory", "ProjectRepair"],
            "gui_status": "PASSED" if gui_complete else "GUI_INTEGRATION_INCOMPLETE", "gui_checkpoints": gui.records,
            "control_port_closed": True, "sample_port_closed": True, "owned_process_tree_closed": True})
        if not gui_complete:
            raise SampleTestError("GUI_INTEGRATION_INCOMPLETE")
        print("默认官方示例验收完成。", flush=True)
    except Exception as error:
        primary_failure = error
        try:
            failure_cleanup = _cleanup_after_failure(client, state, identities)
        except Exception as cleanup_error:
            failure_cleanup = {"cleanup_error": type(cleanup_error).__name__}
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:
                pass
        process_tree_closed = process is None
        if process is not None:
            try:
                if process.poll() is None and failure_cleanup.get("shutdown_requested"):
                    try:
                        process.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        pass
                if process.poll() is None:
                    terminate_process_tree(process, timeout=10)
                else:
                    release_process_tree(process, timeout=5)
                process_tree_closed = process_tree_has_exited(process)
            except Exception as cleanup_error:
                failure_cleanup["process_tree_cleanup_error"] = type(cleanup_error).__name__
                process_tree_closed = False
        if log is not None:
            log.close()
        if primary_failure is not None:
            try:
                _write_failure(
                    audit_dir,
                    primary_failure,
                    state,
                    failure_cleanup,
                    control_closed=not _port_open(CONTROL_PORT),
                    sample_closed=None if sample_port is None else not _port_open(sample_port),
                    process_tree_closed=process_tree_closed,
                )
            except Exception as artifact_error:
                print(
                    f"failure artifact write failed: {type(artifact_error).__name__}",
                    file=sys.stderr,
                    flush=True,
                )
    if primary_failure is not None:
        raise primary_failure
