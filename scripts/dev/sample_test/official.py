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
    1: "界鉴真实启动",
    2: "进入 Agent 写错的问题版",
    3: "一键应用公开样例合同",
    4: "三条权限路径与检查准备",
    5: "问题版真实检查",
    6: "Agent 获取修复合同并修改代码",
    7: "修复版独立复验",
    8: "证据受限实验检查",
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


def _start_official_experience(
    page: Page,
    client: ApiClient,
    audit_dir: Path,
    state: HarnessState,
) -> dict[str, object]:
    """从未接入工作台进入问题版；UI 提示先讲矛盾，启动本身不产生检查结论。"""

    page.goto(client.origin, wait_until="networkidle")
    page.get_by_role("button", name="启动官方示例").click()
    page.get_by_text("启动示例不会开始真实检查，也不会预先生成结论。").wait_for()
    with page.expect_response(
        lambda response: response.request.method == "POST"
        and response.url.endswith("/api/experience/official-sample/start"),
        timeout=30_000,
    ) as pending:
        page.get_by_role("button", name="启动问题版").click()
    response = pending.value
    if response.status != 200:
        try:
            payload = response.json()
        except PlaywrightError:
            payload = {}
        error = payload.get("error") if isinstance(payload, dict) else None
        code = error.get("code") if isinstance(error, dict) else "请求失败"
        page.screenshot(path=str(audit_dir / "official-start-failed.png"), full_page=True)
        raise SampleTestError(f"官方示例启动返回 {response.status}: {code}")
    state.sample_started = True
    page.wait_for_url("**/#/workspace", timeout=30_000)
    page.get_by_role(
        "button",
        name="一键应用样例配置",
        exact=True,
    ).wait_for(timeout=30_000)
    page.screenshot(path=str(audit_dir / "official-problem-version.png"), full_page=True)
    status = client.call("GET", "/api/experience/official-sample")
    if (
        not status.get("active")
        or status.get("scenario_version") != "VULNERABLE"
        or status.get("scenario_prepared") is not False
    ):
        raise SampleTestError("官方示例没有形成等待配置的问题版体验")
    if _project_run_ids(client, str(status["project_id"])):
        raise SampleTestError("启动问题版时不应预先生成检查记录")
    return status


def _prepare_official_scenario(
    page: Page,
    client: ApiClient,
    audit_dir: Path,
    project_id: str,
) -> tuple[dict[str, str], dict[str, str], str]:
    """通过唯一一键入口应用公开合同，再从正式产品查询结果核对全部输入事实。"""

    before_prepare = _project_run_ids(client, project_id)
    with page.expect_response(
        lambda response: response.request.method == "POST"
        and response.url.endswith("/api/experience/official-sample/prepare"),
        timeout=30_000,
    ) as pending:
        page.get_by_role("button", name="一键应用样例配置").click()
    if pending.value.status != 200:
        raise SampleTestError(f"一键样例配置返回 {pending.value.status}")
    if _project_run_ids(client, project_id) != before_prepare:
        raise SampleTestError("一键样例配置不应创建检查记录")
    page.get_by_role("button", name="检查问题版").wait_for(timeout=30_000)
    page.screenshot(path=str(audit_dir / "official-contract-ready.png"), full_page=True)
    status = client.call("GET", "/api/experience/official-sample")
    change_id = status.get("vulnerable_change_id")
    if (
        status.get("scenario_prepared") is not True
        or status.get("scenario_version") != "VULNERABLE"
        or not isinstance(change_id, str)
        or re.fullmatch(r"chg_[0-9a-f]{32}", change_id) is None
    ):
        raise SampleTestError("一键样例配置没有形成问题版合同与真实代码变化")

    understanding = client.call("GET", f"/api/projects/{project_id}/application-understanding")
    role_ids = {
        str(role["canonical_key"]).casefold(): str(role["candidate_id"])
        for role in understanding["role_candidates"]
        if role.get("decision") == "CONFIRMED"
        and str(role["canonical_key"]).casefold() in ROLE_LABELS
    }
    if set(role_ids) != set(ROLE_LABELS):
        raise SampleTestError("一键合同没有确认 Alice 与 Bob 对应的两个权限组")
    action_ids = {
        str(action["canonical_key"]): str(action["candidate_id"])
        for action in understanding["action_candidates"]
        if action.get("decision") == "CONFIRMED"
        and str(action["canonical_key"]) in {EXPORT_ACTION_KEY, VIEW_ACTION_KEY}
    }
    if set(action_ids) != {EXPORT_ACTION_KEY, VIEW_ACTION_KEY}:
        raise SampleTestError("一键合同没有确认导出与日常资料查看两个业务动作")
    identities = client.call("GET", f"/api/projects/{project_id}/test-identities")
    by_role = {
        str(item["role_canonical_key"]).casefold(): item
        for item in identities
        if item.get("status") == "PREPARED"
    }
    if set(ROLE_LABELS) - set(by_role):
        raise SampleTestError("一键合同没有准备 Alice 与 Bob 的测试账号")
    return (
        {key: str(by_role[key]["identity_id"]) for key in ROLE_LABELS},
        action_ids,
        change_id,
    )


def _switch_official_version(
    client: ApiClient,
    version: str,
    *,
    source_run_id: str | None = None,
) -> dict[str, object]:
    """只切换样例实现或观察能力；调用方仍须独立创建 Run。"""

    status = client.call(
        "POST",
        "/api/experience/official-sample/version",
        {
            "schema_version": "1",
            "version": version,
            "source_run_id": source_run_id,
        },
    )
    if status.get("scenario_version") != version:
        raise SampleTestError(f"官方示例没有切换到 {version}")
    return status


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


def _check_submission_body(
    client: ApiClient,
    *,
    name: str,
    change_id: str | None = None,
    verification_run_id: str | None = None,
) -> dict[str, object]:
    """让自动验收与正式检查页使用同一个修复变化上下文。"""

    body: dict[str, object] = {
        "schema_version": "1",
        "idempotency_key": f"sample-{name}-{uuid4().hex}",
    }
    if verification_run_id is not None:
        status = client.call("GET", "/api/experience/official-sample")
        repair_change_id = status.get("repair_change_id")
        if not isinstance(repair_change_id, str) or re.fullmatch(
            r"chg_[0-9a-f]{32}", repair_change_id
        ) is None:
            raise SampleTestError(f"{name} 没有形成可用于正式重验的修复变化")
        if change_id is not None and change_id != repair_change_id:
            raise SampleTestError(f"{name} 指定的变化不是当前权威修复变化")
        change_id = repair_change_id
    if change_id is not None:
        body["change_id"] = change_id
    return body


def _run_case(
    client: ApiClient,
    project_id: str,
    identities: dict[str, str],
    state: HarnessState,
    *,
    name: str,
    expected_verdict: str,
    expected_issue: str,
    action_ids: dict[str, str],
    change_id: str | None = None,
    verification_run_id: str | None = None,
    expected_source_statuses: dict[str, str] | None = None,
) -> dict[str, object]:
    client.call(
        "POST",
        f"/api/projects/{project_id}/check-preparation",
        {"schema_version": "1", "change_id": change_id},
    )
    submitted = client.call(
        "POST",
        f"/api/projects/{project_id}/checks",
        _check_submission_body(
            client,
            name=name,
            change_id=change_id,
            verification_run_id=verification_run_id,
        ),
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
    if len(evidence) != 3:
        raise SampleTestError(f"{name} 未发布三条正式路径的 Evidence")
    export_evidence = tuple(
        item
        for item in evidence
        if (item.get("case_snapshot") or {}).get("action_id")
        == action_ids[EXPORT_ACTION_KEY]
    )
    if len(export_evidence) != 2:
        raise SampleTestError(f"{name} 未发布一组导出差分 Evidence")
    for item in export_evidence:
        _assert_six_sources(item)
    bob = next(
        (
            item
            for item in export_evidence
            if (item.get("case_snapshot") or {}).get("subject_id") == identities["member"]
        ),
        None,
    )
    if bob is None or bob.get("verdict") != expected_issue:
        raise SampleTestError(f"{name} 的普通成员 Evidence 结论不正确")
    bob_view = next(
        (
            item
            for item in evidence
            if (item.get("case_snapshot") or {}).get("subject_id") == identities["member"]
            and (item.get("case_snapshot") or {}).get("action_id")
            == action_ids[VIEW_ACTION_KEY]
        ),
        None,
    )
    view_facts = (bob_view or {}).get("security_effect_facts") or []
    if (
        bob_view is None
        or bob_view.get("verdict") != "SAFE"
        or (bob_view.get("execution_fact") or {}).get("outcome") != "ACCEPTED"
        or not view_facts
        or view_facts[0].get("kind") != "DATA_DISCLOSURE"
        or view_facts[0].get("state") != "CONFIRMED"
    ):
        raise SampleTestError(f"{name} 的 Bob 日常资料查看路径没有保持安全可用")
    issue = next(
        (
            item
            for item in presentation["issues"]
            if item["planned_identity_id"] == identities["member"]
            and item["action_id"] == action_ids[EXPORT_ACTION_KEY]
        ),
        None,
    )
    if issue is None:
        raise SampleTestError(f"{name} 缺少普通成员结果投影")
    if [(item["observer_type"], item["label"], item["role"]) for item in issue["evidence_sources"]] != list(SOURCE_LABELS):
        raise SampleTestError(f"{name} 的六来源角色投影不正确")
    for observer_type, expected_status in (expected_source_statuses or {}).items():
        actual_status = next(
            (
                item.get("status")
                for item in issue["evidence_sources"]
                if item.get("observer_type") == observer_type
            ),
            None,
        )
        if actual_status != expected_status:
            raise SampleTestError(
                f"{name} 的 {observer_type} 状态不是 {expected_status}"
            )
    if verification_run_id is not None:
        repair = presentation.get("repair_verification") or {}
        path_results = repair.get("path_results") or []
        if (
            repair.get("status") != "VERIFIED"
            or len(path_results) != 3
            or {item.get("kind") for item in path_results}
            != {"DENY_EFFECT_REMOVAL", "ALLOW_CONTROL", "REGRESSION_CONTROL"}
            or any(item.get("status") != "VERIFIED" for item in path_results)
        ):
            raise SampleTestError(f"{name} 没有分别证明三条修复路径")
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


def _project_run_ids(client: ApiClient, project_id: str) -> list[str]:
    """读取当前应用的正式检查记录，用于证明准备与版本切换没有暗中生成结论。"""

    runs = client.call("GET", f"/api/projects/{project_id}/runs")
    if not isinstance(runs, list):
        raise SampleTestError("当前应用的检查记录不是公共列表")
    return [str(item["run_id"]) for item in runs]


def _assert_history_view(
    page: Page,
    origin: str,
    history: Mapping[str, object],
    audit_dir: Path,
) -> None:
    """按后端 History 的长期权限视图核对默认页面，不依赖次级 Finding 聚合。"""

    page.goto(origin + "/#/history", wait_until="networkidle")
    page.get_by_role("heading", name="历史变化", exact=True).wait_for(timeout=30_000)
    intents = history.get("intents")
    if not isinstance(intents, list) or not intents:
        raise SampleTestError("History 没有形成可展示的长期权限要求")
    expected_markers: set[str] = set()
    for intent in intents:
        if not isinstance(intent, dict):
            raise SampleTestError("History 权限要求不是公共对象")
        display_label = intent.get("display_label")
        if not isinstance(display_label, str) or not display_label:
            raise SampleTestError("History 权限要求缺少展示标签")
        page.get_by_text(display_label, exact=True).first.wait_for(timeout=30_000)
        runs = intent.get("runs")
        if not isinstance(runs, list):
            raise SampleTestError("History 权限要求缺少关联 Run")
        for run in runs:
            if not isinstance(run, dict):
                continue
            if run.get("association_status") == "EXACT":
                expected_markers.add("可可靠关联")
                if run.get("verdict") == "INCONCLUSIVE":
                    expected_markers.add("证据不足")
            elif run.get("association_status") == "POLICY_ONLY":
                expected_markers.add("仅确认属于本轮策略")
            if run.get("repair_status") == "VERIFIED":
                expected_markers.add("原考题复验通过")
    for marker in expected_markers:
        page.get_by_text(marker, exact=True).first.wait_for(timeout=30_000)
    page.screenshot(path=str(audit_dir / "history.png"), full_page=True)


def _assert_verification_view(
    page: Page,
    origin: str,
    result: dict[str, object],
    audit_dir: Path,
    *,
    name: str,
    verify_interactions: bool = False,
) -> None:
    """在 2560×1440 首屏核对现场验证，并只使用公开可见交互。"""

    presentation = result["presentation"]
    if not isinstance(presentation, dict):
        raise SampleTestError(f"{name} 缺少正式 ResultPresentation")
    page.set_viewport_size({"width": 2560, "height": 1440})
    # 每个真实 Run 都重新挂载应用，避免同一 hash 路由沿用上一次 Run 的内存态。
    page.goto(
        origin + f"/?sample_state={name}#/verification",
        wait_until="networkidle",
    )
    page.get_by_role("heading", name="现场验证", exact=True).wait_for(timeout=30_000)
    board = page.locator(".verification-board")
    board.wait_for(timeout=30_000)
    if board.locator(":scope > .verification-column").count() != 3:
        raise SampleTestError(f"{name} 的现场验证不是固定三栏")

    page.screenshot(path=str(audit_dir / f"verification-{name}-2560x1440.png"))
    required = [
        ("权限考题", page.get_by_role("heading", name="权限考题已锁定", exact=True)),
        ("业务路径", page.get_by_role("heading", name="预期与实际业务路径", exact=True)),
        ("主张边界", page.get_by_role("heading", name="现有证据能够确认什么", exact=True)),
    ]
    verdict = str(presentation.get("verdict"))
    if verdict == "BLOCK":
        issue = (presentation.get("issues") or [{}])[0]
        diagnosis = issue.get("diagnosis") or {}
        precision = str(diagnosis.get("precision"))
        if precision == "EXACT":
            required.append(("精确断裂", page.get_by_text("红色边表示首个可证明断裂。", exact=True)))
        elif precision == "RANGE":
            required.append(("断裂区间", page.get_by_text("只能确认断裂发生在两个边界之间，不能声称唯一断点。", exact=True)))
        else:
            required.append(("违规定位边界", page.get_by_text("违规已确认，但当前证据不足以定位具体断裂点", exact=True)))
    elif verdict == "INCONCLUSIVE":
        required.append(("证据不足", page.get_by_text("证据不足，现场不标记红色断裂点", exact=True)))
    if (presentation.get("repair_verification") or {}).get("status") == "VERIFIED":
        required.append(("原考题复验", page.get_by_text("原考题复验已通过", exact=True).first))
    for label, locator in required:
        locator.wait_for(timeout=30_000)
        bounds = locator.bounding_box()
        if bounds is None or bounds["y"] < 0 or bounds["y"] + bounds["height"] > 1440:
            raise SampleTestError(f"{name} 的{label}没有出现在 2560×1440 首屏")

    if verify_interactions:
        interaction_step = "打开证据说明"
        try:
            node = page.locator("button.verification-path-node").first
            node.wait_for(timeout=30_000)
            node.click()
            page.get_by_text("为什么属于本轮", exact=True).first.wait_for(timeout=30_000)

            interaction_step = "关闭证据说明"
            drawer = page.locator(".ant-drawer-content-wrapper")
            page.locator(".ant-drawer-close").click()
            drawer.wait_for(state="hidden", timeout=30_000)

            interaction_step = "查看证据限制"
            page.get_by_role("button", name="查看限制", exact=True).click()
            if page.evaluate("document.activeElement?.id") != "verification-limitations":
                raise SampleTestError(f"{name} 的查看限制没有聚焦证据边界")
        except PlaywrightError as error:
            raise SampleTestError(f"{name} 的{interaction_step}交互失败") from error


def _switch_official_version_through_ui(
    page: Page,
    client: ApiClient,
    audit_dir: Path,
    version: str,
    *,
    source_run_id: str | None = None,
) -> dict[str, object]:
    """核对版本说明后从真实按钮切换；切换完成仍不创建 Run 或写入 Verdict。"""

    controls = {
        "VULNERABLE": (
            "问题版",
            "进入 Agent 写错的问题版？",
            "模拟 Vibe Coding Agent 为缩短导出等待",
            "确认切换",
            "workspace",
            "official-switched-vulnerable.png",
        ),
        "EVIDENCE_LIMITED": (
            "证据受限实验",
            "进入证据受限实验？",
            "模拟两条关键业务结果观察暂时不可用",
            "确认切换",
            "workspace",
            "official-switched-evidence-limited.png",
        ),
        "FIXED": (
            "交给 Agent 修复",
            "把界鉴修复意见交给 Agent？",
            "Codex 通过 MCP 读取界鉴",
            "生成修改并切换",
            "workspace",
            "official-switched-fixed.png",
        ),
    }
    if version not in controls:
        raise SampleTestError(f"未知官方示例版本：{version}")
    current = client.call("GET", "/api/experience/official-sample")
    project_id = current.get("project_id")
    if not isinstance(project_id, str):
        raise SampleTestError("官方示例缺少当前应用")
    before_switch = _project_run_ids(client, project_id)
    button_label, title, explanation, confirm_label, route, filename = controls[version]
    page.goto(client.origin + "/#/workspace", wait_until="networkidle")
    button = page.get_by_role("button", name=button_label, exact=True)
    button.wait_for(timeout=30_000)
    if button.is_disabled():
        raise SampleTestError(f"官方示例当前不能进入{button_label}")
    button.click()
    page.get_by_role("dialog", name=title, exact=True).wait_for(timeout=30_000)
    page.get_by_text(explanation, exact=False).wait_for(timeout=30_000)
    if version == "FIXED":
        if source_run_id is None:
            raise SampleTestError("修复版缺少来源 BLOCK 检查")
        page.get_by_text(source_run_id, exact=False).wait_for(timeout=30_000)
        page.get_by_text("authorization_policy.py", exact=False).wait_for(timeout=30_000)
    with page.expect_response(
        lambda response: response.request.method == "POST"
        and response.url.endswith("/api/experience/official-sample/version"),
        timeout=30_000,
    ) as pending:
        page.get_by_role("button", name=confirm_label, exact=True).click()
    if pending.value.status != 200:
        raise SampleTestError(f"官方示例切换 {version} 返回 {pending.value.status}")
    if _project_run_ids(client, project_id) != before_switch:
        raise SampleTestError("版本切换不应创建检查记录")
    page.wait_for_url(re.compile(rf"#/{route}$"), timeout=30_000)
    status = client.call("GET", "/api/experience/official-sample")
    if status.get("scenario_version") != version:
        raise SampleTestError(f"官方示例没有切换到 {version}")
    if version == "FIXED":
        repair_change_id = status.get("repair_change_id")
        if not isinstance(repair_change_id, str) or re.fullmatch(
            r"chg_[0-9a-f]{32}", repair_change_id
        ) is None:
            raise SampleTestError("Agent 修复没有形成真实代码变化")
    page.screenshot(path=str(audit_dir / filename), full_page=True)
    return status


def _assert_workspace_viewports(page: Page, origin: str, audit_dir: Path) -> None:
    """核对亮暗 2.5K、响应式入口和测试页随滚动可用的操作栏。"""

    def assert_no_horizontal_overflow(label: str) -> None:
        overflow = page.evaluate(
            """() => {
                const viewport = document.documentElement.clientWidth;
                const offenders = [...document.querySelectorAll('body *')]
                    .map((element) => {
                        const rect = element.getBoundingClientRect();
                        return {
                            selector: `${element.tagName.toLowerCase()}${element.id ? `#${element.id}` : ''}${[...element.classList].slice(0, 3).map((name) => `.${name}`).join('')}`,
                            left: Math.round(rect.left),
                            right: Math.round(rect.right),
                        };
                    })
                    .filter((item) => item.left < -1 || item.right > viewport + 1)
                    .sort((left, right) => Math.max(Math.abs(right.left), right.right - viewport) - Math.max(Math.abs(left.left), left.right - viewport))
                    .slice(0, 3);
                return {
                    viewport,
                    content: Math.max(
                        document.documentElement.scrollWidth,
                        document.body.scrollWidth,
                    ),
                    offenders,
                };
            }"""
        )
        if overflow["content"] > overflow["viewport"] + 1:
            offenders = ", ".join(
                f"{item['selector']}[{item['left']},{item['right']}]"
                for item in overflow["offenders"]
            ) or "未定位到可见元素"
            raise SampleTestError(
                f"{label} 出现横向溢出：内容 {overflow['content']}px，视口 {overflow['viewport']}px；"
                f"撑宽元素：{offenders}"
            )

    page.set_viewport_size({"width": 2560, "height": 1440})
    for route, heading in (
        ("workspace", "工作台"),
        ("changes", "变化"),
        ("permissions", "权限"),
        ("tests", "测试"),
    ):
        page.goto(origin + f"/#/{route}", wait_until="networkidle")
        page.get_by_role("heading", name=heading, exact=True).first.wait_for(
            timeout=30_000
        )
    page.goto(origin + "/#/workspace", wait_until="networkidle")
    if not page.locator(".module-navigation").is_visible():
        raise SampleTestError("2560×1440 下四模块导航不可见")
    assert_no_horizontal_overflow("2560×1440 工作区")
    page.screenshot(path=str(audit_dir / "workspace-2560x1440.png"), full_page=True)

    theme_button = page.get_by_label(re.compile("切换界面主题"))
    theme_button.click()
    page.get_by_text("暗色主题", exact=True).click()
    page.wait_for_function("document.documentElement.dataset.theme === 'dark'")
    page.locator(".ant-dropdown:not(.ant-dropdown-hidden)").wait_for(state="hidden")
    if page.evaluate("getComputedStyle(document.body).backgroundColor") != "rgb(13, 17, 23)":
        raise SampleTestError("暗色主题没有使用正式产品背景色")
    if page.locator(".topbar-tools .ant-btn").first.evaluate("element => getComputedStyle(element).color") != "rgb(242, 245, 248)":
        raise SampleTestError("暗色主题顶部即时状态的文字对比度不足")
    assert_no_horizontal_overflow("2560×1440 暗色工作区")
    page.screenshot(path=str(audit_dir / "workspace-2560x1440-dark.png"), full_page=True)
    page.get_by_label("切换界面主题，当前：暗色").click()
    page.get_by_text("亮色主题", exact=True).click()
    page.wait_for_function("document.documentElement.dataset.theme === 'light'")
    page.locator(".ant-dropdown:not(.ant-dropdown-hidden)").wait_for(state="hidden")

    page.set_viewport_size({"width": 1280, "height": 900})
    if not page.locator(".module-navigation").is_visible():
        raise SampleTestError("1280px 下桌面四模块导航不可见")
    assert_no_horizontal_overflow("1280×900 工作区")
    page.screenshot(path=str(audit_dir / "workspace-1280x900.png"), full_page=True)

    page.set_viewport_size({"width": 600, "height": 900})
    if page.locator(".module-navigation").is_visible():
        raise SampleTestError("600px 下仍显示桌面四模块导航")
    trigger = page.get_by_label("打开持续验证工作区")
    trigger.wait_for(timeout=30_000)
    assert_no_horizontal_overflow("600×900 工作区")
    page.screenshot(path=str(audit_dir / "workspace-600x900.png"), full_page=True)
    trigger.click()
    mobile_navigation = page.get_by_role("navigation", name="持续验证工作区")
    mobile_navigation.last.wait_for(timeout=30_000)
    page.screenshot(path=str(audit_dir / "workspace-600x900-navigation.png"), full_page=True)
    page.keyboard.press("Escape")
    mobile_navigation.last.wait_for(state="hidden", timeout=30_000)

    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(origin + "/#/validation", wait_until="networkidle")
    page.get_by_role("heading", name="验证运行", exact=True).wait_for(timeout=30_000)
    action_bar = page.locator(".task-action-bar")
    action_bar.wait_for(timeout=30_000)
    for scroll_ratio in (0, 0.5, 1):
        state = page.evaluate(
            """(ratio) => {
                const maximum = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
                window.scrollTo(0, maximum * ratio);
                const rect = document.querySelector('.task-action-bar')?.getBoundingClientRect();
                return rect ? { top: rect.top, bottom: rect.bottom, viewport: window.innerHeight, maximum } : null;
            }""",
            scroll_ratio,
        )
        if not state or state["top"] < -1 or state["bottom"] > state["viewport"] + 1:
            raise SampleTestError(f"验证运行页底部操作栏没有随页面滚动保持可用：{state}")
    page.screenshot(path=str(audit_dir / "validation-actions-1280x900.png"))
    page.set_viewport_size({"width": 2560, "height": 1440})


def _assert_presentation_mode(page: Page, origin: str, audit_dir: Path) -> None:
    """从正式工作台进入一例四幕，证明展示只重排当前官方样例事实。"""

    page.set_viewport_size({"width": 2560, "height": 1440})
    page.goto(origin + "/#/workspace", wait_until="networkidle")
    page.get_by_role("button", name="进入完整展示", exact=True).click()
    navigation = page.get_by_role("navigation", name="展示章节")
    navigation.wait_for(timeout=30_000)
    acts = (
        ("发现矛盾", "403 与 ZIP 的矛盾", "presentation-01-conflict.png"),
        ("回看变化", "人的规则、提交变化与界鉴核对", "presentation-02-change.png"),
        ("展开证据", "权限要求、实际执行与真实后果", "presentation-03-evidence.png"),
        ("验证修复", "修复合同", "presentation-04-repair.png"),
    )
    for label, fact_region, filename in acts:
        button = navigation.get_by_role("button", name=re.compile(label))
        button.click()
        if button.get_attribute("aria-current") != "step":
            raise SampleTestError(f"展示章节没有切换到：{label}")
        heading = page.locator(".presentation-page-heading h2")
        heading.wait_for(timeout=30_000)
        if not heading.inner_text().strip():
            raise SampleTestError(f"展示章节缺少主结论：{label}")
        page.get_by_label(fact_region, exact=True).wait_for(timeout=30_000)
        if page.locator(".presentation-content .ant-skeleton").count() != 0:
            raise SampleTestError(f"展示章节仍在加载正式事实：{label}")
        page.screenshot(path=str(audit_dir / filename), full_page=True)
    page.get_by_role("button", name="返回工作台", exact=True).click()
    page.get_by_role("heading", name="工作台", exact=True).first.wait_for(
        timeout=30_000
    )


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
    human_result = _run_cli(root, var_dir, environment, "result", "show", "--run", run_id)
    human_history = _run_cli(root, var_dir, environment, "history", "--project", project_id)
    if not human_result or not human_history:
        raise SampleTestError("CLI Human 结果或历史输出不完整")
    json_result = json.loads(_run_cli(root, var_dir, environment, "--json", "result", "show", "--run", run_id))["data"]
    json_history = json.loads(_run_cli(root, var_dir, environment, "--json", "history", "--project", project_id))["data"]
    if json_result != run["presentation"]:
        raise SampleTestError("CLI JSON 结果与服务关闭前的 API 结果不一致")
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

        _phase(state, 2)
        experience = _start_official_experience(page, client, audit_dir, state)
        project_id = str(experience["project_id"])
        origin = str(experience["origin"])
        sample_port = int(origin.rsplit(":", 1)[1])

        _phase(state, 3)
        identities, action_ids, vulnerable_change_id = _prepare_official_scenario(
            page,
            client,
            audit_dir,
            project_id,
        )

        _phase(state, 4)
        preview = client.call("GET", f"/api/projects/{project_id}/check-preview")
        if (
            preview.get("ready") is not True
            or preview.get("case_count") != 3
            or preview.get("differential_pair_count") != 1
        ):
            raise SampleTestError("公开样例合同没有形成三条权限路径与一组导出对照")
        page.goto(client.origin + "/#/tests", wait_until="networkidle")
        page.get_by_role("heading", name="测试", exact=True).wait_for(timeout=30_000)
        page.get_by_text(
            "当前权限规则和测试条件已经可以开始检查。",
            exact=True,
        ).wait_for(timeout=30_000)
        page.screenshot(path=str(audit_dir / "official-three-paths-ready.png"), full_page=True)
        if stop_after_setup:
            if verify_workspace_ui:
                _assert_workspace_viewports(page, client.origin, audit_dir)
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
                    "scenario_setup_probe": "passed",
                    "case_count": 3,
                    "differential_pair_count": 1,
                    "workspace_ui_probe": "passed" if verify_workspace_ui else "not-run",
                    "control_port_closed": True,
                    "sample_port_closed": True,
                    "owned_process_tree_closed": True,
                },
            )
            return

        _phase(state, 5)
        vulnerable = _run_case(
            client,
            project_id,
            identities,
            state,
            name="vulnerable",
            expected_verdict="BLOCK",
            expected_issue="VULNERABLE",
            action_ids=action_ids,
            change_id=vulnerable_change_id,
        )
        _assert_verification_view(
            page,
            client.origin,
            vulnerable,
            audit_dir,
            name="block",
            verify_interactions=True,
        )

        _phase(state, 6)
        _switch_official_version_through_ui(
            page,
            client,
            audit_dir,
            "FIXED",
            source_run_id=str(vulnerable["run_id"]),
        )

        _phase(state, 7)
        fixed = _run_case(
            client,
            project_id,
            identities,
            state,
            name="fixed",
            expected_verdict="PASS",
            expected_issue="SAFE",
            action_ids=action_ids,
            verification_run_id=str(vulnerable["run_id"]),
        )
        _assert_verification_view(
            page,
            client.origin,
            fixed,
            audit_dir,
            name="repair-verified",
        )
        _assert_presentation_mode(page, client.origin, audit_dir)

        _phase(state, 8)
        evidence_limited_status = _switch_official_version_through_ui(
            page,
            client,
            audit_dir,
            "EVIDENCE_LIMITED",
        )
        evidence_change_id = evidence_limited_status.get("vulnerable_change_id")
        if not isinstance(evidence_change_id, str):
            raise SampleTestError("证据受限版没有形成当前问题代码变化")
        inconclusive = _run_case(
            client,
            project_id,
            identities,
            state,
            name="observation-limited",
            expected_verdict="INCONCLUSIVE",
            expected_issue="INCONCLUSIVE",
            action_ids=action_ids,
            change_id=evidence_change_id,
            expected_source_statuses={
                "OWNER_API": "UNAVAILABLE",
                "AZURE_BLOB_OBJECT": "UNAVAILABLE",
            },
        )
        _assert_verification_view(
            page,
            client.origin,
            inconclusive,
            audit_dir,
            name="inconclusive",
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
        _assert_history_view(page, client.origin, history, audit_dir)
        _assert_workspace_viewports(page, client.origin, audit_dir)

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
                "scenario_versions": ["VULNERABLE", "FIXED", "EVIDENCE_LIMITED"],
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
