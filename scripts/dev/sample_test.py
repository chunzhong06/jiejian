# 自动 L5 总编排：从真实 start.cmd 启动产品并验证 GUI、Sample、Recording、Verification 与安全退出。

from __future__ import annotations

import argparse
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
from sample_test_windows import RecordingWindowDriver, WindowsL5Error, window_snapshot


PROJECT_KEY = "campus-digital-museum"
RESOURCE_ID = "campus-digital-museum-package"
EXPORT_ACTION_KEY = "POST /api/projects/{project_id}/exports"
CONTROL_PORT = 8765
PHASE_TITLES = {
    1: "界鉴真实启动",
    2: "官方示例与应用理解",
    3: "测试身份",
    4: "真实 Recording 与安全恢复",
    5: "权限要求与检查准备",
    6: "漏洞行为检查",
    7: "修复行为检查",
    8: "观察受限检查",
    9: "GUI / CLI / JSON 等价",
    10: "Report / History / Evidence / Resource Cleanup",
}
ROLE_LABELS = {
    "project_owner": "项目负责人",
    "member": "普通成员",
}
SOURCE_LABELS = (
    ("OWNER_API", "目标业务状态", "KEY"),
    ("READ_ONLY_SQLITE", "只读数据库", "SUPPORTING"),
    ("STRUCTURED_AUDIT_LOG", "结构化审计记录", "SUPPORTING"),
    ("ASYNC_TASK_STATUS", "后台任务", "SUPPORTING"),
    ("AZURE_QUEUE_PEEK", "消息通道", "SUPPORTING"),
    ("AZURE_BLOB_OBJECT", "最终对象/文件", "KEY"),
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
    """保存失败清理所需的最小公开身份与当前十阶段。"""

    stage: int = 0
    recording_id: str | None = None
    recording_job_id: str | None = None
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
    print(f"[{number}/10] {PHASE_TITLES[number]}", flush=True)


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


def _start_guided_experience(
    page: Page,
    client: ApiClient,
    audit_dir: Path,
    state: HarnessState,
) -> dict[str, object]:
    page.goto(client.origin, wait_until="networkidle")
    page.get_by_role("button", name="评委导览").click()
    page.get_by_text("不会开始真实安全检查，也不会预先生成检查结论。").wait_for()
    with page.expect_response(
        lambda response: response.request.method == "POST"
        and response.url.endswith("/api/experience/official-sample/start"),
        timeout=30_000,
    ) as pending:
        page.get_by_role("button", name="同意并开始").click()
    response = pending.value
    if response.status != 200:
        try:
            payload = response.json()
        except PlaywrightError:
            payload = {}
        error = payload.get("error") if isinstance(payload, dict) else None
        code = error.get("code") if isinstance(error, dict) else "请求失败"
        page.screenshot(path=str(audit_dir / "guided-start-failed.png"), full_page=True)
        raise SampleTestError(f"评委导览启动返回 {response.status}: {code}")
    state.sample_started = True
    page.wait_for_url("**/#/application", timeout=30_000)
    page.get_by_label("评委导览").wait_for()
    page.screenshot(path=str(audit_dir / "guided-application.png"), full_page=True)
    status = client.call("GET", "/api/experience/official-sample")
    if not status.get("active") or status.get("experience_mode") != "GUIDED":
        raise SampleTestError("评委导览没有形成活跃的 GUIDED 体验")
    return status


def _confirm_understanding(client: ApiClient, project_id: str) -> tuple[dict[str, str], str]:
    understanding = client.call("GET", f"/api/projects/{project_id}/application-understanding")
    revision = int(understanding["revision"])
    role_ids: dict[str, str] = {}
    for role in understanding["role_candidates"]:
        key = str(role["canonical_key"]).casefold()
        if key not in ROLE_LABELS:
            continue
        understanding = client.call(
            "PUT",
            f"/api/projects/{project_id}/roles/{role['candidate_id']}",
            {
                "schema_version": "1",
                "decision": "CONFIRMED",
                "display_name": ROLE_LABELS[key],
                "revision": revision,
            },
        )
        revision = int(understanding["revision"])
        role_ids[key] = role["candidate_id"]
    if set(role_ids) != set(ROLE_LABELS):
        raise SampleTestError("官方示例未发现精确的两个权限组候选")
    action_id = ""
    for action in understanding["action_candidates"]:
        selected = action["canonical_key"] == EXPORT_ACTION_KEY
        understanding = client.call(
            "PUT",
            f"/api/projects/{project_id}/actions/{action['candidate_id']}",
            {
                "schema_version": "1",
                "decision": "CONFIRMED" if selected else "REJECTED",
                "display_name": "导出完整项目资料包" if selected else action["display_name"],
                "revision": revision,
            },
        )
        revision = int(understanding["revision"])
        if selected:
            action_id = action["candidate_id"]
    if not action_id:
        raise SampleTestError("官方示例未发现导出资料包动作候选")
    return role_ids, action_id


def _prepare_identities(
    client: ApiClient,
    project_id: str,
) -> dict[str, str]:
    prepared = client.call("POST", "/api/experience/official-sample/identities", {"schema_version": "1"})
    if not prepared.get("identities_ready"):
        raise SampleTestError("官方示例测试账号未全部准备完成")
    identities = client.call("GET", f"/api/projects/{project_id}/test-identities")
    by_role = {
        str(item["role_canonical_key"]).casefold(): item
        for item in identities
        if item.get("status") == "PREPARED"
    }
    if set(ROLE_LABELS) - set(by_role):
        raise SampleTestError("测试账号与三个已确认权限组不一致")
    return {key: str(by_role[key]["identity_id"]) for key in ROLE_LABELS}


def _merge_recording_ui_steps(
    client: ApiClient,
    recording_id: str,
    draft: dict[str, Any],
) -> dict[str, Any]:
    # UIA 的确认按钮可能形成独立 UI 事件；必须经正式 Review 与随后请求归并。
    while True:
        steps = list(draft.get("steps") or [])
        ui_index = next(
            (index for index, step in enumerate(steps) if step.get("method") is None),
            None,
        )
        if ui_index is None:
            return draft
        if ui_index + 1 >= len(steps) or steps[ui_index + 1].get("method") is None:
            raise SampleTestError("真实 Recording UI 动作无法与相邻网络请求归并")
        view = client.call(
            "POST",
            f"/api/recordings/{recording_id}/review",
            {
                "schema_version": "1",
                "command": {
                    "schema_version": "1",
                    "operation": "MERGE_ADJACENT_STEPS",
                    "left_step_id": steps[ui_index]["id"],
                    "right_step_id": steps[ui_index + 1]["id"],
                },
            },
        )
        draft = view["draft"]


def _record_flow(
    client: ApiClient,
    project_id: str,
    action_id: str,
    alice_id: str,
    chromium_executable: Path,
    state: HarnessState,
) -> str:
    before = window_snapshot()
    created = client.call(
        "POST",
        f"/api/projects/{project_id}/recordings",
        {
            "schema_version": "1",
            "action_candidate_id": action_id,
            "test_identity_id": alice_id,
            "duration_seconds": 90,
            "idempotency_key": f"sample-recording-{uuid4().hex}",
        },
        accepted=(202,),
    )
    recording_id = str(created["recording"]["recording_id"])
    state.recording_id = recording_id
    state.recording_job_id = str(created["job"]["job_id"])
    _wait_for(
        lambda: client.call("GET", f"/api/recordings/{recording_id}"),
        lambda view: view.get("capture_phase") == "AWAITING_CAPTURE",
        timeout=45,
        label="录制浏览器准备",
    )
    driver = RecordingWindowDriver(before, chromium_executable)
    driver.wait_until_ready(timeout=30)
    client.call("POST", f"/api/recordings/{recording_id}/capture/start", {"schema_version": "1"})
    _wait_for(
        lambda: client.call("GET", f"/api/recordings/{recording_id}"),
        lambda view: view.get("capture_phase") == "CAPTURING",
        timeout=15,
        label="录制开始",
    )
    driver.run_business_flow()
    client.call("POST", f"/api/recordings/{recording_id}/capture/stop", {"schema_version": "1"})
    view = _wait_for(
        lambda: client.call("GET", f"/api/recordings/{recording_id}"),
        lambda item: (item.get("recording") or {}).get("state") in {"PENDING_REVIEW", "FAILED", "SAFETY_STOPPED"},
        timeout=45,
        label="录制处理完成",
    )
    recording_state = (view.get("recording") or {}).get("state")
    if recording_state != "PENDING_REVIEW" or (view.get("job") or {}).get("state") != "SUCCEEDED":
        raise SampleTestError(f"真实 Recording 未进入审阅成功状态: {recording_state}")
    draft = view.get("draft") or {}
    for variable in draft.get("variables") or []:
        source = variable["candidate_sources"][0]
        view = client.call(
            "POST",
            f"/api/recordings/{recording_id}/review",
            {
                "schema_version": "1",
                "command": {
                    "schema_version": "1",
                    "operation": "CONFIRM_VARIABLE_SOURCE",
                    "variable_name": variable["name"],
                    "source_event_sequence": source["source_event_sequence"],
                    "source_json_path": source["json_path"],
                },
            },
        )
        draft = view["draft"]
    draft = _merge_recording_ui_steps(client, recording_id, draft)
    target = next(
        (step for step in draft["steps"] if step.get("method") == "POST" and str(step.get("path") or "").split("?", 1)[0].endswith("/exports")),
        None,
    )
    if target is None:
        raise SampleTestError("真实 Recording 没有形成导出目标步骤")
    recovery = next(
        (
            step
            for step in draft["steps"]
            if step.get("method") == "DELETE"
            and str(step.get("path") or "").split("?", 1)[0].endswith("/exports")
        ),
        None,
    )
    if recovery is None:
        raise SampleTestError("真实 Recording 没有形成导出撤销步骤")
    view = client.call(
        "POST",
        f"/api/recordings/{recording_id}/review",
        {"schema_version": "1", "command": {"schema_version": "1", "operation": "CONFIRM_TARGET_STEP", "step_id": target["id"]}},
    )
    draft = view["draft"]
    target = next(step for step in draft["steps"] if step["id"] == target["id"])
    resource = next(
        (item for item in target["resource_candidates"] if item["consumer"] == "JSON_BODY" and item["location"] == "$.resource_id"),
        None,
    )
    if resource is None:
        raise SampleTestError("真实 Recording 没有形成 JSON 资源候选")
    client.call(
        "POST",
        f"/api/recordings/{recording_id}/review",
        {"schema_version": "1", "command": {"schema_version": "1", "operation": "CONFIRM_RESOURCE_SLOT", "candidate_id": resource["candidate_id"]}},
    )
    client.call("POST", f"/api/recordings/{recording_id}/finalize", {"schema_version": "1"})
    return recording_id


def _confirm_safety(
    client: ApiClient,
    recording_id: str,
    alice_id: str,
) -> None:
    view = client.call("GET", f"/api/recordings/{recording_id}/safety-setup")
    resource = next(
        (item for item in view["resource_candidates"] if item["actual_resource_id"] == RESOURCE_ID and item["consumer"] == "JSON_BODY"),
        None,
    )
    observation = next((item for item in view["observation_candidates"] if item["method"] == "GET"), None)
    recovery = next((item for item in view["recovery_candidates"] if item["method"] == "DELETE"), None)
    effect = next((item for item in view["security_effect_candidates"] if item["kind"] == "OBJECT_CREATION"), None)
    if not all((resource, observation, recovery, effect)):
        raise SampleTestError("真实业务流程没有形成完整的资源、观察、恢复与副作用候选")
    confirmed = client.call(
        "PUT",
        f"/api/recordings/{recording_id}/safety-setup",
        {
            "schema_version": "1",
            "resource_candidate_id": resource["candidate_id"],
            "logical_name": "校园数字展馆完整项目资料包",
            "resource_type": "项目资料包",
            "owner_test_identity_id": alice_id,
            "observation_candidate_id": observation["candidate_id"],
            "recovery_candidate_id": recovery["candidate_id"],
            "confirm_recovery_not_required": False,
            "security_effect_candidate_id": effect["candidate_id"],
        },
    )
    if confirmed.get("automatic_execution_allowed") is not True:
        raise SampleTestError("完整安全恢复设置未允许自动执行")


def _confirm_permissions(
    client: ApiClient,
    project_id: str,
    action_id: str,
    role_ids: dict[str, str],
) -> None:
    owner_id = role_ids["project_owner"]
    for subject, relation, expectation in (
        (owner_id, "OWNS", "ALLOW"),
        (role_ids["member"], "OTHER_ROLE", "DENY"),
    ):
        client.call(
            "PUT",
            f"/api/projects/{project_id}/permission-intents/{action_id}/{subject}/{owner_id}/{relation}",
            {"schema_version": "1", "expectation": expectation, "actor": "官方示例验收"},
        )
    client.call(
        "POST",
        f"/api/projects/{project_id}/security-setup/compile",
        {"schema_version": "1", "actor": "官方示例验收"},
    )
    preview = client.call("GET", f"/api/projects/{project_id}/check-preview")
    if preview.get("ready") is not True or preview.get("case_count") != 2:
        raise SampleTestError("检查预览未形成同一动作的两个正式权限用例")


def _wait_for_published_result(
    client: ApiClient,
    run_id: str,
    run_job_id: str,
) -> dict[str, object]:
    detail = _wait_for(
        lambda: client.call("GET", f"/api/runs/{run_id}"),
        lambda item: item.get("lifecycle") in {"FAILED", "CANCELLED", "SAFETY_STOPPED"}
        or (item.get("finalization") or {}).get("base_report_state") in {"COMPLETE", "FAILED"},
        timeout=180,
        label=f"Run {run_id} 发布结果",
    )
    if detail.get("lifecycle") != "COMPLETED" or detail.get("result_integrity") != "VERIFIED":
        raise SampleTestError(
            "L5_RUN_RESULT_UNAVAILABLE: "
            f"lifecycle={detail.get('lifecycle')} "
            f"integrity={detail.get('result_integrity')} "
            f"run_id={run_id} run_job_id={run_job_id}"
        )
    return detail


def _load_evidence(
    client: ApiClient,
    run_id: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """分别保留发布索引与完整文档，避免跨控制面比较不同层级的事实。"""

    evidence_index = client.call("GET", f"/api/runs/{run_id}/evidence")
    evidence_documents = [
        client.call("GET", f"/api/runs/{run_id}/evidence/{item['evidence_id']}")
        for item in evidence_index
    ]
    return evidence_index, evidence_documents


def _assert_six_sources(evidence: dict[str, object]) -> None:
    bindings = evidence["requirement_bindings"]
    outcomes = evidence["outcomes"]
    facts = evidence["observation_facts"]
    if not (len(bindings) == len(outcomes) == len(facts) == 6):
        raise SampleTestError("已发布 Evidence 未包含六个真实观察来源")
    by_observer = {item["observer_id"]: item for item in bindings}
    if {item["observer_type"] for item in by_observer.values()} != SOURCE_TYPES:
        raise SampleTestError("Evidence 观察来源类型与官方示例合同不一致")
    if {item["observer_id"] for item in outcomes} != set(by_observer):
        raise SampleTestError("Evidence 观察结果与来源绑定不一致")
    if {item["requirement_id"] for item in facts} != {item["requirement_id"] for item in bindings}:
        raise SampleTestError("Evidence 观察事实与需求绑定不一致")


def _run_case(
    client: ApiClient,
    project_id: str,
    identities: dict[str, str],
    state: HarnessState,
    *,
    name: str,
    authorization_order: str,
    blob_observation: str,
    expected_verdict: str,
    expected_issue: str,
    verification_run_id: str | None = None,
) -> dict[str, object]:
    behavior: dict[str, object] = {
        "schema_version": "1",
        "authorization_order": authorization_order,
        "blob_observation": blob_observation,
        "verification_run_id": verification_run_id,
    }
    client.call("POST", "/api/experience/official-sample/behavior", behavior)
    client.call(
        "POST",
        f"/api/projects/{project_id}/security-setup/compile",
        {"schema_version": "1", "actor": "官方示例验收"},
    )
    submitted = client.call(
        "POST",
        f"/api/projects/{project_id}/checks",
        {"schema_version": "1", "idempotency_key": f"sample-{name}-{uuid4().hex}"},
        accepted=(202,),
    )
    run_id = str(submitted["run"]["run_id"])
    run_job_id = str(submitted["job"]["job_id"])
    state.active_run_id = run_id
    state.active_run_job_id = run_job_id
    detail = _wait_for_published_result(client, run_id, run_job_id)
    presentation = client.call("GET", f"/api/runs/{run_id}/presentation")
    if detail.get("verdict") != expected_verdict or presentation.get("verdict") != expected_verdict:
        raise SampleTestError(f"{name} 的正式结果不是 {expected_verdict}")
    evidence_index, evidence = _load_evidence(client, run_id)
    if len(evidence) != 2:
        raise SampleTestError(f"{name} 未发布两个权限用例的 Evidence")
    for item in evidence:
        _assert_six_sources(item)
    bob = next(
        (item for item in evidence if (item.get("case_snapshot") or {}).get("subject_id") == identities["member"]),
        None,
    )
    if bob is None or bob.get("verdict") != expected_issue:
        raise SampleTestError(f"{name} 的普通成员 Evidence 结论不正确")
    issue = next(
        (item for item in presentation["issues"] if item["planned_identity_id"] == identities["member"]),
        None,
    )
    if issue is None:
        raise SampleTestError(f"{name} 缺少普通成员结果投影")
    if [(item["observer_type"], item["label"], item["role"]) for item in issue["evidence_sources"]] != list(SOURCE_LABELS):
        raise SampleTestError(f"{name} 的六来源角色投影不正确")
    reports = client.call("GET", f"/api/runs/{run_id}/reports")
    if not reports:
        raise SampleTestError(f"{name} 没有发布可读报告")
    report = client.call("GET", f"/api/runs/{run_id}/reports/{reports[0]['report_id']}")
    if report.get("run_id") != run_id or (report.get("presentation") or {}).get("verdict") != expected_verdict:
        raise SampleTestError(f"{name} 报告与正式结果不一致")
    html = client.raw(f"/api/runs/{run_id}/reports/{reports[0]['report_id']}/view")
    if b"<html" not in html.lower():
        raise SampleTestError(f"{name} 报告没有可读 HTML 视图")
    return {
        "run_id": run_id,
        "verdict": expected_verdict,
        "presentation": presentation,
        "evidence_index": evidence_index,
        "evidence": evidence,
    }


def _assert_history(client: ApiClient, project_id: str, runs: list[dict[str, object]]) -> dict[str, object]:
    history = client.call("GET", f"/api/projects/{project_id}/results/history")
    comparisons = history["comparisons"]
    if [item["run_id"] for item in comparisons] != [item["run_id"] for item in runs]:
        raise SampleTestError("History 没有按同一项目的三次正式结果排序")
    statuses = [{item["status"] for item in comparison["changes"]} for comparison in comparisons]
    if "NEW" not in statuses[0] or "FIXED" not in statuses[1] or "INCONCLUSIVE" not in statuses[2]:
        raise SampleTestError("History 没有形成新发现、已解决、证据不足的连续语义")
    if "FIXED" in statuses[2]:
        raise SampleTestError("后续证据不足被错误显示为已解决")
    return history


def _run_cli(
    root: Path,
    var_dir: Path,
    environment: Mapping[str, str],
    *arguments: str,
) -> str:
    result = subprocess.run(
        [sys.executable, "-B", "-m", "product.backend.cli", "--var-dir", str(var_dir), *arguments],
        cwd=root,
        env=dict(environment),
        text=True,
        encoding="utf-8",
        errors="strict",
        capture_output=True,
        check=False,
        timeout=60,
    )
    if result.returncode != 0:
        raise SampleTestError(f"CLI {' '.join(arguments)} 失败，退出码 {result.returncode}")
    return result.stdout.strip()


def _assert_cli_equivalence(
    root: Path,
    var_dir: Path,
    project_id: str,
    run: dict[str, object],
    history: dict[str, object],
    environment: Mapping[str, str],
) -> None:
    run_id = str(run["run_id"])
    human_result = _run_cli(root, var_dir, environment, "--human", "result", "show", "--run", run_id)
    human_evidence = _run_cli(root, var_dir, environment, "--human", "result", "evidence", "--run", run_id)
    human_history = _run_cli(root, var_dir, environment, "--human", "history", "show", "--project", project_id)
    if not human_result or "已发布证据：2 项" not in human_evidence or not human_history:
        raise SampleTestError("CLI Human 结果、证据或历史输出不完整")
    json_result = json.loads(_run_cli(root, var_dir, environment, "--json", "result", "show", "--run", run_id))["data"]
    json_evidence = json.loads(_run_cli(root, var_dir, environment, "--json", "result", "evidence", "--run", run_id))["data"]
    json_history = json.loads(_run_cli(root, var_dir, environment, "--json", "history", "show", "--project", project_id))["data"]
    if json_result != run["presentation"]:
        raise SampleTestError("CLI JSON 结果与服务关闭前的 API 结果不一致")
    if (
        json_evidence.get("run_id") != run_id
        or json_evidence.get("evidence") != run["evidence_index"]
    ):
        raise SampleTestError(
            f"L5_CLI_EVIDENCE_INDEX_MISMATCH: run_id={run_id}"
        )
    if json_history != history:
        raise SampleTestError("CLI JSON History 与服务关闭前的 API History 不一致")


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

    if isinstance(error, (SampleTestError, WindowsL5Error)):
        summary = str(error)
        token = summary.split(":", 1)[0]
        code = token if re.fullmatch(r"[A-Z][A-Z0-9_]+", token) else type(error).__name__.upper()
        return code, summary[:512]
    if isinstance(error, PlaywrightError):
        return "PLAYWRIGHT_ERROR", "Playwright 自动化边界失败"
    return type(error).__name__.upper(), "自动 L5 出现未分类失败"


def _recording_snapshot(client: ApiClient, state: HarnessState) -> dict[str, object] | None:
    if state.recording_id is None:
        return None
    view = client.call("GET", f"/api/recordings/{state.recording_id}")
    recording = view.get("recording") or {}
    job = view.get("job") or {}
    return {
        "capture_phase": view.get("capture_phase"),
        "recording_state": recording.get("state"),
        "job_state": job.get("state"),
    }


def _recording_state_closed(snapshot: Mapping[str, object] | None) -> bool:
    if snapshot is None:
        return True
    job_state = snapshot.get("job_state")
    recording_state = snapshot.get("recording_state")
    job_terminal = job_state in {"SUCCEEDED", "FAILED", "CANCELLED"}
    recording_terminal = recording_state in {
        "PENDING_REVIEW",
        "COMPLETED",
        "FAILED",
        "CANCELLED",
        "SAFETY_STOPPED",
    }
    return job_terminal and recording_terminal


def _wait_recording_job_terminal(
    client: ApiClient,
    state: HarnessState,
    *,
    timeout: float,
) -> dict[str, object] | None:
    """给正式 Recording 收口留出有界时间，超时后由调用方决定是否取消 Job。"""

    deadline = time.monotonic() + timeout
    latest: dict[str, object] | None = None
    while time.monotonic() < deadline:
        try:
            latest = _recording_snapshot(client, state)
        except SampleTestError:
            time.sleep(0.2)
            continue
        if latest is None or latest.get("job_state") in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            return latest
        time.sleep(0.2)
    return latest


def _cleanup_after_failure(
    client: ApiClient,
    state: HarnessState,
    identities: Mapping[str, str],
) -> dict[str, object]:
    """按公开 API 收口 Recording、身份、Sample 和控制面，不覆盖主错误。"""

    report: dict[str, object] = {"actions": []}
    actions = report["actions"]
    assert isinstance(actions, list)
    if not state.product_ready:
        report.update(
            {
                "before": None,
                "after": None,
                "state_closed": True,
                "shutdown_requested": False,
            }
        )
        return report
    try:
        before = _recording_snapshot(client, state)
        report["before"] = before
        if before is not None and before.get("capture_phase") == "CAPTURING":
            client.call(
                "POST",
                f"/api/recordings/{state.recording_id}/capture/stop",
                {"schema_version": "1"},
            )
            actions.append("capture.stop")
            before = _wait_recording_job_terminal(
                client,
                state,
                timeout=15,
            )
        if (
            before is not None
            and state.recording_job_id is not None
            and before.get("job_state") not in {"SUCCEEDED", "FAILED", "CANCELLED"}
        ):
            client.call("POST", f"/api/jobs/{state.recording_job_id}/cancel")
            actions.append("job.cancel")
            _wait_for(
                lambda: _recording_snapshot(client, state),
                lambda item: item is not None and item.get("job_state") in {"SUCCEEDED", "FAILED", "CANCELLED"},
                timeout=20,
                label="失败后的录制作业终态",
            )
        report["after"] = _wait_for(
            lambda: _recording_snapshot(client, state),
            _recording_state_closed,
            timeout=15,
            label="失败后的 Recording 状态收口",
        )
        report["state_closed"] = True
    except Exception as error:
        report["recording_cleanup_error"] = type(error).__name__
        try:
            report["after"] = _recording_snapshot(client, state)
        except Exception:
            report["after"] = None
        report["state_closed"] = _recording_state_closed(report["after"])
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
            "recording_id": state.recording_id,
            "recording_job_id": state.recording_job_id,
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
    client.call("POST", "/api/system/shutdown", {"schema_version": "1"}, accepted=(202,))
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
    stop_after_recording: bool = False,
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
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        client.bind_page(page)

        _phase(state, 2)
        experience = _start_guided_experience(page, client, audit_dir, state)
        project_id = str(experience["project_id"])
        origin = str(experience["origin"])
        sample_port = int(origin.rsplit(":", 1)[1])
        role_ids, action_id = _confirm_understanding(client, project_id)

        _phase(state, 3)
        identities = _prepare_identities(client, project_id)

        _phase(state, 4)
        recording_id = _record_flow(
            client,
            project_id,
            action_id,
            identities["project_owner"],
            source_runtime.playwright_executable,
            state,
        )
        _confirm_safety(client, recording_id, identities["project_owner"])
        if stop_after_recording:
            _shutdown_owned_runtime(
                client,
                state,
                identities,
                browser,
                playwright,
                process,
                var_dir,
                sample_port,
            )
            browser = None
            playwright = None
            process = None
            state.product_ready = False
            _write_summary(
                audit_dir,
                {
                    "schema_version": "1",
                    "recording_id": recording_id,
                    "recording_probe": "passed",
                    "control_port_closed": True,
                    "sample_port_closed": True,
                    "owned_process_tree_closed": True,
                },
            )
            return

        _phase(state, 5)
        _confirm_permissions(client, project_id, action_id, role_ids)

        _phase(state, 6)
        vulnerable = _run_case(
            client,
            project_id,
            identities,
            state,
            name="vulnerable",
            authorization_order="ENQUEUE_BEFORE_AUTHORIZE",
            blob_observation="AVAILABLE",
            expected_verdict="BLOCK",
            expected_issue="VULNERABLE",
        )

        _phase(state, 7)
        fixed = _run_case(
            client,
            project_id,
            identities,
            state,
            name="fixed",
            authorization_order="AUTHORIZE_BEFORE_ENQUEUE",
            blob_observation="AVAILABLE",
            expected_verdict="PASS",
            expected_issue="SAFE",
            verification_run_id=str(vulnerable["run_id"]),
        )

        _phase(state, 8)
        inconclusive = _run_case(
            client,
            project_id,
            identities,
            state,
            name="observation-limited",
            authorization_order="AUTHORIZE_BEFORE_ENQUEUE",
            blob_observation="UNAVAILABLE",
            expected_verdict="INCONCLUSIVE",
            expected_issue="INCONCLUSIVE",
        )
        runs = [vulnerable, fixed, inconclusive]
        history = _assert_history(client, project_id, runs)

        _phase(state, 9)
        page.goto(client.origin + "/#/results", wait_until="networkidle")
        expected_presentation = inconclusive["presentation"]
        result_headline = page.locator("#result-headline")
        result_headline.wait_for(timeout=30_000)
        if result_headline.inner_text().strip() != str(expected_presentation["headline"]):
            raise SampleTestError("GUI 结果页与正式 ResultPresentation 的结论不一致")
        visible_counts = {
            "".join(value.split())
            for value in page.locator(".result-count-grid > div").all_inner_texts()
        }
        expected_counts = {
            f"实际检查{expected_presentation['checked_count']}项",
            f"符合预期{expected_presentation['safe_count']}项",
            f"权限问题{expected_presentation['problem_count']}项",
            f"证据不足{expected_presentation['inconclusive_count']}项",
            f"未覆盖{expected_presentation['uncovered_count']}项",
        }
        if visible_counts != expected_counts:
            raise SampleTestError("GUI 结果页与正式 ResultPresentation 的数量摘要不一致")
        issue_title = str(expected_presentation["issues"][0]["title"])
        page.get_by_role("heading", name=issue_title, exact=True).wait_for(timeout=30_000)
        page.screenshot(path=str(audit_dir / "latest-result.png"), full_page=True)
        page.goto(client.origin + "/#/history", wait_until="networkidle")
        page.get_by_text("已解决", exact=True).first.wait_for(timeout=30_000)
        page.get_by_text("证据不足", exact=True).first.wait_for(timeout=30_000)
        page.screenshot(path=str(audit_dir / "history.png"), full_page=True)

        _phase(state, 10)
        _shutdown_owned_runtime(
            client,
            state,
            identities,
            browser,
            playwright,
            process,
            var_dir,
            sample_port,
        )
        browser = None
        playwright = None
        process = None
        state.product_ready = False
        if source_runtime is None:
            raise SampleTestError("SOURCE_RUNTIME_UNAVAILABLE")
        _assert_cli_equivalence(
            root,
            var_dir,
            project_id,
            inconclusive,
            history,
            source_runtime.environment,
        )
        _write_summary(
            audit_dir,
            {
                "schema_version": "1",
                "project_id": project_id,
                "recording_id": recording_id,
                "runs": [{"run_id": item["run_id"], "verdict": item["verdict"]} for item in runs],
                "control_port_closed": True,
                "sample_port_closed": True,
                "owned_process_tree_closed": True,
            },
        )
        print("自动 L5 技术验收完成。", flush=True)
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the official sample delivery validation.")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--var-dir", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        run(arguments.root, arguments.var_dir)
    except Exception as exc:
        code, summary = _failure_identity(exc)
        print(f"sample-test failed: {code}: {summary}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
